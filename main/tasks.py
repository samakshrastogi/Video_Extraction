# ================= IMPORTS =================
import os
import subprocess
import json
import re
import uuid
import cv2
import logging
import heapq
import math
from decimal import Decimal
from celery import shared_task
import boto3
from datetime import datetime, timedelta
from django.db import transaction
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from main.utils.global_terminal_dashboard import dashboard
from main.models import (
    Video,
    VideoTechnicalMetadata,
    VideoExtendedMetadata,
    VideoCategory,
    VideoFrame,
    VideoProcessingState,
)

logger = logging.getLogger(__name__)

# ================= CONSTANTS =================
START_DATE = datetime(2025, 11, 25)
END_DATE = datetime(2026, 2, 7)

TOP_FRAMES_LIMIT = 20

CPU = max(cpu_count(), 2)
FRAME_SCORE_WORKERS = int(os.getenv("FRAME_SCORE_WORKERS", min(4, CPU)))
S3_UPLOAD_WORKERS = int(os.getenv("S3_UPLOAD_WORKERS", min(6, CPU * 2)))

_ENV_CACHE = None
_S3_CLIENT = None


# ================= ENV / S3 =================
def get_env():
    global _ENV_CACHE
    if _ENV_CACHE:
        return _ENV_CACHE

    env = {
        "S3_ENDPOINT": os.getenv("S3_ENDPOINT"),
        "ACCESS_KEY": os.getenv("ACCESS_KEY"),
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "BUCKET_NAME": os.getenv("BUCKET_NAME"),
    }

    missing = [k for k, v in env.items() if not v]
    if missing:
        raise RuntimeError(f"Missing ENV vars: {missing}")

    _ENV_CACHE = env
    return env


def get_s3():
    global _S3_CLIENT
    if _S3_CLIENT:
        return _S3_CLIENT

    env = get_env()

    _S3_CLIENT = boto3.client(
        "s3",
        endpoint_url=env["S3_ENDPOINT"],
        aws_access_key_id=env["ACCESS_KEY"],
        aws_secret_access_key=env["SECRET_KEY"],
        config=Config(max_pool_connections=50, retries={"max_attempts": 5}),
    )
    return _S3_CLIENT


# ================= SAFE HELPERS =================
def safe_decimal(val):
    try:
        if val is None:
            return None
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return Decimal(str(val)).quantize(Decimal("1.0000"))
    except:
        return None


def safe_int(val):
    try:
        return int(val) if val else None
    except:
        return None


def safe_float(val):
    try:
        return float(val) if val else None
    except:
        return None


# ================= UTILS =================
def clean_title(filename):
    name = filename.replace(".mp4", "")
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"[^A-Za-z0-9 ]", "", name)
    return name.title()


def generate_uploaded_date(filename):
    total_days = (END_DATE - START_DATE).days
    seed = abs(hash(filename)) % max(total_days, 1)
    return START_DATE + timedelta(days=seed)


def get_or_create_category(folder_name):
    name = folder_name.replace("-", " ").title()
    return VideoCategory.objects.get_or_create(name=name)[0]


# ================= FFPROBE =================
def ffprobe_full(url):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,bit_rate,size,format_name",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,avg_frame_rate,channels,"
            "pix_fmt,bits_per_raw_sample,nb_frames,sample_rate,bit_rate",
            "-of",
            "json",
            url,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if not res.stdout:
            return {}

        data = json.loads(res.stdout)
        format_info = data.get("format", {})
        streams = data.get("streams", [])

        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

        meta = {}

        duration_sec = safe_float(format_info.get("duration"))
        meta["duration_ms"] = int(duration_sec * 1000) if duration_sec else None
        meta["bitrate"] = safe_int(format_info.get("bit_rate"))
        meta["file_size"] = safe_int(format_info.get("size"))
        meta["container_format"] = format_info.get("format_name")

        if video:
            w, h = video.get("width"), video.get("height")
            if w and h:
                meta["resolution"] = f"{w}x{h}"
                meta["orientation"] = "landscape" if w >= h else "portrait"

            meta["video_codec"] = video.get("codec_name")
            meta["pixel_format"] = video.get("pix_fmt")
            meta["bit_depth"] = safe_int(video.get("bits_per_raw_sample"))
            meta["frame_count"] = safe_int(video.get("nb_frames"))

            fps_raw = video.get("avg_frame_rate", "0/1")
            try:
                num, den = map(int, fps_raw.split("/"))
                meta["fps"] = round(num / den, 3) if den else None
            except:
                meta["fps"] = None

        if audio:
            meta["audio_codec"] = audio.get("codec_name")
            meta["audio_channels"] = safe_int(audio.get("channels"))
            meta["audio_sample_rate"] = safe_int(audio.get("sample_rate"))
            meta["audio_bitrate"] = safe_int(audio.get("bit_rate"))

        return meta

    except Exception as e:
        logger.error(f"[FFPROBE FAIL] {url} -> {e}")
        return {}


# ================= FRAME SCORE =================
def calculate_frame_score(image_path):
    try:
        img = cv2.imread(image_path)
        if img is None:
            return 0

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = gray.mean()
        brightness_score = 255 - abs(127 - brightness)
        contrast = gray.std()

        return sharpness * 0.6 + brightness_score * 0.2 + contrast * 0.2
    except:
        return 0


# ================= FRAME EXTRACTION =================
def extract_keyframes_and_store(url, filename, key, video_obj):

    env = get_env()
    s3 = get_s3()

    name = filename.rsplit(".", 1)[0]
    category_folder = key.split("/")[0]

    temp_dir = f"/tmp/keyframes_{uuid.uuid4().hex}"
    os.makedirs(temp_dir, exist_ok=True)

    raw_pattern = f"{temp_dir}/raw_%06d.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-threads",
            "2",
            "-loglevel",
            "error",
            "-skip_frame",
            "nokey",
            "-i",
            url,
            "-vsync",
            "0",
            raw_pattern,
        ],
        check=True,
        timeout=1200,
    )

    raw_frames = [f for f in os.listdir(temp_dir) if f.startswith("raw_")]

    scored_frames = []

    def score_frame(i, raw_file):
        raw_path = os.path.join(temp_dir, raw_file)
        final_path = os.path.join(temp_dir, f"frame_{i}.jpg")
        os.rename(raw_path, final_path)
        score = calculate_frame_score(final_path)
        return (score, final_path, i)

    with ThreadPoolExecutor(max_workers=FRAME_SCORE_WORKERS) as executor:
        futures = [
            executor.submit(score_frame, i, raw_file)
            for i, raw_file in enumerate(raw_frames, start=1)
        ]
        for f in as_completed(futures):
            try:
                scored_frames.append(f.result())
            except:
                pass

    best_frames = heapq.nlargest(TOP_FRAMES_LIMIT, scored_frames)

    frame_objs = []

    def upload_frame(frame_tuple):
        score, frame_path, frame_number = frame_tuple

        s3_key = f"{category_folder}/frames_s/{name}/frame_{frame_number}.jpg"

        s3.upload_file(
            frame_path,
            env["BUCKET_NAME"],
            s3_key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )

        return VideoFrame(
            video=video_obj,
            frame_s3_key=s3_key,
            frame_number=frame_number,
            frame_type="key",
            thumbnail_score=safe_decimal(score),
        )

    with ThreadPoolExecutor(max_workers=S3_UPLOAD_WORKERS) as executor:
        futures = [executor.submit(upload_frame, f) for f in best_frames]
        for f in as_completed(futures):
            try:
                frame_objs.append(f.result())
            except:
                pass

    if frame_objs:
        VideoFrame.objects.bulk_create(frame_objs, ignore_conflicts=True)

    # mark thumb
    if best_frames:
        _, _, best_frame_number = max(best_frames)
        VideoFrame.objects.filter(video=video_obj).update(frame_type="key")
        VideoFrame.objects.filter(
            video=video_obj, frame_number=best_frame_number
        ).update(frame_type="thumb")

    try:
        for f in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, f))
        os.rmdir(temp_dir)
    except:
        pass

    return len(best_frames)


# ================= PROCESS VIDEO TASK =================
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_kwargs={"max_retries": 3},
)
def process_video_task(self, key, size_from_s3=None):

    video_obj = None

    try:
        env = get_env()

        filename = key.split("/")[-1]
        category_folder = key.split("/")[0]
        db_url = f"videos/{filename}"

        category_obj = get_or_create_category(category_folder)
        url = f"{env['S3_ENDPOINT']}/{env['BUCKET_NAME']}/{key}"

        # ===== SINGLE DB FETCH =====
        video_obj = (
            Video.objects.select_related("tech", "extended")
            .filter(video_url=db_url)
            .first()
        )

        if video_obj:
            state = VideoProcessingState.objects.filter(video=video_obj).first()
            if state and state.status == "completed":
                return "Already processed"

        meta = ffprobe_full(url)
        if not meta:
            raise RuntimeError("Metadata empty")

        if size_from_s3 and not meta.get("file_size"):
            meta["file_size"] = size_from_s3

        uploaded_date = generate_uploaded_date(filename)

        with transaction.atomic():
            video_obj, _ = Video.objects.update_or_create(
                video_url=db_url,
                defaults={
                    "title": clean_title(filename),
                    "category": category_obj,
                    "uploaded_date": uploaded_date.date(),
                },
            )

            VideoProcessingState.objects.update_or_create(
                video=video_obj,
                defaults={"status": "processing"},
            )

        # ===== CONDITIONAL META UPSERT =====
        if not getattr(video_obj, "tech", None):
            VideoTechnicalMetadata.objects.update_or_create(
                video=video_obj,
                defaults={
                    "resolution": meta.get("resolution"),
                    "orientation": meta.get("orientation"),
                    "duration_ms": meta.get("duration_ms"),
                    "fps": meta.get("fps"),
                    "bitrate": meta.get("bitrate"),
                    "video_codec": meta.get("video_codec"),
                    "audio_codec": meta.get("audio_codec"),
                    "audio_channels": meta.get("audio_channels"),
                    "file_size": meta.get("file_size"),
                },
            )

        if not getattr(video_obj, "extended", None):
            VideoExtendedMetadata.objects.update_or_create(
                video=video_obj,
                defaults={
                    "frame_count": meta.get("frame_count"),
                    "pixel_format": meta.get("pixel_format"),
                    "bit_depth": meta.get("bit_depth"),
                    "container_format": meta.get("container_format"),
                    "audio_sample_rate": meta.get("audio_sample_rate"),
                    "audio_bitrate": meta.get("audio_bitrate"),
                },
            )

        # ===== FRAME CHECK =====
        frames_exist = VideoFrame.objects.filter(video=video_obj).exists()

        if frames_exist:
            frames_count = VideoFrame.objects.filter(video=video_obj).count()
        else:
            frames_count = extract_keyframes_and_store(url, filename, key, video_obj)

        VideoProcessingState.objects.update_or_create(
            video=video_obj,
            defaults={
                "status": "completed",
                "frames_extracted": True,
                "thumbnails_generated": True,
            },
        )

        logger.info(f"[TASK OK] {filename} frames={frames_count}")
        return "Success"

    except Exception as e:
        logger.error(f"[TASK FAIL] {key} -> {e}")

        if video_obj:
            VideoProcessingState.objects.update_or_create(
                video=video_obj,
                defaults={"status": "failed", "last_error": str(e)},
            )

        raise


# ================= OPTIMIZED S3 SCAN =================
@shared_task
def scan_s3_and_queue_videos():

    try:
        env = get_env()
        s3 = get_s3()

        existing_db_videos = set(Video.objects.values_list("video_url", flat=True))

        processing_states = dict(
            VideoProcessingState.objects.select_related("video").values_list(
                "video__video_url", "status"
            )
        )

        paginator = s3.get_paginator("list_objects_v2")

        queued = 0
        dashboard.queue_stats["pending"] = 0

        for page in paginator.paginate(Bucket=env["BUCKET_NAME"]):
            for obj in page.get("Contents", []):

                key = obj.get("Key")

                if not key or not key.lower().endswith(".mp4"):
                    continue
                if "/videos/" not in key:
                    continue

                filename = key.split("/")[-1]
                db_url = f"videos/{filename}"

                state = processing_states.get(db_url)

                if db_url not in existing_db_videos or state != "completed":
                    process_video_task.delay(key, obj.get("Size"))
                    queued += 1
                    dashboard.queue_stats["pending"] = queued

        logger.info(f"[SCAN DONE] queued={queued}")
        dashboard.queue_stats["pending"] = 0
        return queued

    except Exception as e:
        logger.error(f"[SCAN FAIL] {e}")
        raise
