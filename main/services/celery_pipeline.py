import os
import django
import logging
import boto3
from dotenv import load_dotenv
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from main.utils.global_terminal_dashboard import dashboard

# ================= INIT =================
load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "video_extraction.settings")
django.setup()

from main.tasks import process_video_task
from main.models import Video, VideoProcessingState

# ================= ENV =================
S3_ENDPOINT = os.getenv("S3_ENDPOINT")
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")

BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", 50))
S3_MAX_POOL = int(os.getenv("S3_MAX_POOL", 64))

PIPELINE_PAGE_WORKERS = int(os.getenv("PIPELINE_PAGE_WORKERS", min(4, cpu_count())))

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("celery_pipeline")


# ================= ENV VALIDATION =================
def validate_env():
    required = {
        "S3_ENDPOINT": S3_ENDPOINT,
        "ACCESS_KEY": ACCESS_KEY,
        "SECRET_KEY": SECRET_KEY,
        "BUCKET_NAME": BUCKET_NAME,
    }

    missing = [k for k, v in required.items() if not v]

    if missing:
        raise RuntimeError(f"Missing ENV vars: {missing}")


# ================= S3 CLIENT =================
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        config=Config(
            max_pool_connections=S3_MAX_POOL,
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


# ================= LOAD DB STATE =================
def load_existing_state():

    logger.info("Loading DB state...")

    existing_urls = set(Video.objects.values_list("video_url", flat=True))

    processing_states = dict(
        VideoProcessingState.objects.select_related("video").values_list(
            "video__video_url", "status"
        )
    )

    logger.info(f"Existing videos: {len(existing_urls)}")
    logger.info(f"Processing states: {len(processing_states)}")

    return existing_urls, processing_states


# ================= PAGE PROCESSOR =================
def process_s3_page(page, existing_urls, processing_states):

    local_batch = []
    local_seen = set()

    scanned = 0
    queued = 0
    skipped = 0

    contents = page.get("Contents") or []

    for obj in contents:

        scanned += 1

        key = obj.get("Key")
        if not key:
            skipped += 1
            continue

        if not key.endswith(".mp4"):
            skipped += 1
            continue

        if "/videos/" not in key:
            skipped += 1
            continue

        filename = key.rsplit("/", 1)[-1]
        db_url = f"videos/{filename}"

        state = processing_states.get(db_url)

        if db_url in existing_urls and state == "completed":
            skipped += 1
            continue

        if db_url in local_seen:
            skipped += 1
            continue

        size = obj.get("Size") or 0

        local_batch.append((key, size))
        local_seen.add(db_url)

        if len(local_batch) >= BATCH_SIZE:
            for k, s in local_batch:
                process_video_task.delay(k, s)
                queued += 1
                dashboard.queue_stats["pending"] += 1
            local_batch.clear()

    # flush last batch
    for k, s in local_batch:
        process_video_task.delay(k, s)
        queued += 1
        dashboard.queue_stats["pending"] += 1

    return scanned, queued, skipped


# ================= MAIN PIPELINE =================
def run_pipeline():

    logger.info("========== CELERY PIPELINE START ==========")
    dashboard.queue_stats["pending"] = 0

    try:

        validate_env()

        s3 = get_s3_client()
        paginator = s3.get_paginator("list_objects_v2")

        existing_urls, processing_states = load_existing_state()

        total_scanned = 0
        total_queued = 0
        total_skipped = 0

        with ThreadPoolExecutor(max_workers=PIPELINE_PAGE_WORKERS) as executor:

            futures = []

            for page in paginator.paginate(Bucket=BUCKET_NAME):
                futures.append(
                    executor.submit(
                        process_s3_page,
                        page,
                        existing_urls,
                        processing_states,
                    )
                )

            for future in as_completed(futures):
                try:
                    scanned, queued, skipped = future.result()
                    total_scanned += scanned
                    total_queued += queued
                    total_skipped += skipped
                except Exception as e:
                    logger.error(f"Page processing failed: {e}")

        logger.info(
            f"Pipeline finished scanned={total_scanned} "
            f"queued={total_queued} skipped={total_skipped}"
        )

        logger.info("========== CELERY PIPELINE END ==========")
        dashboard.queue_stats["pending"] = 0

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")


# ================= ENTRY =================
if __name__ == "__main__":
    run_pipeline()
