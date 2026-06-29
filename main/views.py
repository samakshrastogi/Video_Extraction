import os
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q

from .models import (
    VideoCategory,
    Video,
    VideoFrame,
)

logger = logging.getLogger(__name__)


def category_list_api(request):
    cats = VideoCategory.objects.values("id", "name")
    return JsonResponse({"results": list(cats)})


def video_dashboard(request):
    return render(
        request,
        "video_dashboard.html",
        {
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT", ""),
            "S3_BUCKET": os.getenv("BUCKET_NAME", ""),
        },
    )


def safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def video_metadata_api(request):

    try:

        page = max(safe_int(request.GET.get("page"), 1), 1)
        size = min(max(safe_int(request.GET.get("size"), 50), 1), 200)

        category = request.GET.get("category")
        orientation = request.GET.get("orientation")
        search = request.GET.get("search")

        qs = Video.objects.select_related("category", "tech", "extended", "processing")

        if category:
            qs = qs.filter(category_id=category)

        if orientation:
            qs = qs.filter(tech__orientation=orientation)

        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(video_url__icontains=search))

        total = qs.values("id").count()

        start = (page - 1) * size
        end = start + size

        qs = qs.order_by("-uploaded_date", "-id")[start:end]

        thumb_map = dict(
            VideoFrame.objects.filter(
                video_id__in=[v.id for v in qs],
                frame_type="thumb",
            ).values_list("video_id", "frame_s3_key")
        )

        results = []

        for v in qs:

            tech = getattr(v, "tech", None)
            ext = getattr(v, "extended", None)
            proc = getattr(v, "processing", None)

            duration_sec = None
            if tech and tech.duration_ms:
                duration_sec = round(float(tech.duration_ms) / 1000, 2)

            results.append(
                {
                    "title": v.title,
                    "category": v.category.name if v.category else "",
                    "category_id": v.category.id if v.category else None,
                    "video_url": v.video_url,
                    "uploaded_date": (
                        v.uploaded_date.strftime("%Y-%m-%d")
                        if v.uploaded_date
                        else None
                    ),
                    "processing_status": proc.status if proc else None,
                    "thumbnail_s3_key": thumb_map.get(v.id),
                    "resolution": getattr(tech, "resolution", None),
                    "orientation": getattr(tech, "orientation", None),
                    "duration_seconds": duration_sec,
                    "fps": getattr(tech, "fps", None),
                    "bitrate": getattr(tech, "bitrate", None),
                    "video_codec": getattr(tech, "video_codec", None),
                    "audio_codec": getattr(tech, "audio_codec", None),
                    "audio_channels": getattr(tech, "audio_channels", None),
                    "file_size": getattr(tech, "file_size", None),
                    "frame_count": getattr(ext, "frame_count", None),
                    "pixel_format": getattr(ext, "pixel_format", None),
                    "bit_depth": getattr(ext, "bit_depth", None),
                    "container_format": getattr(ext, "container_format", None),
                    "audio_sample_rate": getattr(ext, "audio_sample_rate", None),
                    "audio_bitrate": getattr(ext, "audio_bitrate", None),
                }
            )

        return JsonResponse(
            {
                "total": total,
                "page": page,
                "size": size,
                "results": results,
            }
        )

    except Exception as e:
        logger.exception("[VIDEO API ERROR]")
        return JsonResponse(
            {"error": "Internal server error", "detail": str(e)},
            status=500,
        )


def video_frames_api(request):

    try:

        video_url = request.GET.get("video_url")

        page = max(safe_int(request.GET.get("page"), 1), 1)
        size = min(max(safe_int(request.GET.get("size"), 50), 1), 200)

        if not video_url:
            return JsonResponse({"error": "video_url required"}, status=400)

        video = (
            Video.objects.only("id", "video_url").filter(video_url=video_url).first()
        )

        if not video:
            return JsonResponse({"error": "video not found"}, status=404)

        qs = VideoFrame.objects.filter(video_id=video.id).only(
            "frame_s3_key",
            "frame_number",
            "timestamp_ms",
            "frame_type",
            "created_at",
        )

        total = qs.count()

        start = (page - 1) * size
        end = start + size

        qs = qs.order_by("frame_number")[start:end]

        results = []

        for f in qs:
            timestamp_sec = (
                round(float(f.timestamp_ms) / 1000, 2)
                if f.timestamp_ms is not None
                else None
            )

            results.append(
                {
                    "frame_s3_key": f.frame_s3_key,
                    "frame_number": f.frame_number,
                    "timestamp_seconds": timestamp_sec,
                    "frame_type": f.frame_type,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
            )

        return JsonResponse(
            {
                "video_url": video.video_url,
                "total": total,
                "page": page,
                "size": size,
                "results": results,
            }
        )

    except Exception as e:
        logger.exception("[VIDEO FRAMES API ERROR]")
        return JsonResponse(
            {"error": "Internal server error", "detail": str(e)},
            status=500,
        )
