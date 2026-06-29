from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import *


def admin_change_url(obj, pk):
    return reverse(
        f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
        args=[pk],
    )


def clickable_id(url, value):
    return format_html('<a href="{}">{}</a>', url, value)


def ms_to_mmss(ms):
    if ms is None:
        return "-"
    total = int(ms / 1000)
    return f"{total//60:02d}:{total%60:02d}"


def bytes_to_mb(size):
    if not size:
        return "-"
    return round(size / (1024 * 1024), 2)


def bps_to_mbps(rate):
    if not rate:
        return "-"
    return round(rate / 1_000_000, 2)


@admin.register(VideoCategory)
class VideoCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("id",)
    show_full_result_count = False


class VideoTechnicalInline(admin.StackedInline):
    model = VideoTechnicalMetadata
    extra = 0
    can_delete = False
    show_change_link = True


class VideoExtendedInline(admin.StackedInline):
    model = VideoExtendedMetadata
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "category_id_link",
        "title",
        "video_url",
        "processing_status_badge",
        "uploaded_date",
        "updated_at",
    )

    search_fields = ("title", "video_url")

    ordering = ("id",)

    list_select_related = ("category", "processing")

    date_hierarchy = "uploaded_date"
    autocomplete_fields = ("category",)
    show_full_result_count = False

    readonly_fields = ("created_at", "updated_at")

    inlines = [
        VideoTechnicalInline,
        VideoExtendedInline,
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("category", "processing")

    def category_id_link(self, obj):
        if not obj.category_id:
            return "-"
        return clickable_id(
            admin_change_url(obj.category, obj.category_id),
            obj.category_id,
        )

    category_id_link.short_description = "Category ID"

    def processing_status_badge(self, obj):
        if not hasattr(obj, "processing") or not obj.processing:
            return "-"
        status = obj.processing.status
        colors = {
            "pending": "gray",
            "processing": "orange",
            "completed": "green",
            "failed": "red",
        }
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(status, "black"),
            status.upper(),
        )

    processing_status_badge.short_description = "Processing"


@admin.register(VideoTechnicalMetadata)
class VideoTechnicalMetadataAdmin(admin.ModelAdmin):

    list_display = (
        "video_id_link",  # ✅ clickable video id
        "resolution",
        "orientation",
        "duration_mmss",
        "fps",
        "bitrate",
        "video_codec",
        "audio_codec",
        "audio_channels",
        "file_size_mb",
    )

    search_fields = (
        "video__title",
        "video_codec",
        "audio_codec",
    )

    list_select_related = ("video",)
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("video")

    def video_id_link(self, obj):
        if not obj.video_id:
            return "-"
        return clickable_id(
            admin_change_url(obj.video, obj.video_id),
            obj.video_id,
        )

    video_id_link.short_description = "Video ID"

    def file_size_mb(self, obj):
        return bytes_to_mb(obj.file_size)

    def duration_mmss(self, obj):
        return ms_to_mmss(obj.duration_ms)


@admin.register(VideoExtendedMetadata)
class VideoExtendedMetadataAdmin(admin.ModelAdmin):

    list_display = (
        "video_id_link",  # ✅ clickable video id
        "frame_count",
        "pixel_format",
        "bit_depth",
        "container_format",
        "audio_sample_rate",
        "audio_bitrate_mbps",
    )

    list_select_related = ("video",)
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("video")

    def video_id_link(self, obj):
        if not obj.video_id:
            return "-"
        return clickable_id(
            admin_change_url(obj.video, obj.video_id),
            obj.video_id,
        )

    video_id_link.short_description = "Video ID"


    def audio_bitrate_mbps(self, obj):
        return bps_to_mbps(obj.audio_bitrate)


@admin.register(VideoFrame)
class VideoFrameAdmin(admin.ModelAdmin):

    list_display = (
        "video_id_link",
        "frame_number",
        "frame_type",
        "thumbnail_score",
        "timestamp_mmss",
        "created_at",
    )

    list_select_related = ("video",)
    date_hierarchy = "created_at"
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("video")

    def video_id_link(self, obj):
        if not obj.video_id:
            return "-"
        return clickable_id(
            admin_change_url(obj.video, obj.video_id),
            obj.video_id,
        )

    video_id_link.short_description = "Video ID"


    def timestamp_mmss(self, obj):
        return ms_to_mmss(obj.timestamp_ms)


@admin.register(VideoProcessingState)
class VideoProcessingStateAdmin(admin.ModelAdmin):

    list_display = (
        "video_id_link",
        "status_badge",
        "frames_extracted",
        "thumbnails_generated",
        "metadata_extracted",
        "retry_count",
        "updated_at",
        "last_processed_at",
    )

    search_fields = (
        "video__title",
        "video__video_url",
        "last_error",
    )

    list_select_related = ("video",)
    date_hierarchy = "updated_at"
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("video")

    def video_id_link(self, obj):
        if not obj.video_id:
            return "-"
        return clickable_id(
            admin_change_url(obj.video, obj.video_id),
            obj.video_id,
        )

    video_id_link.short_description = "Video ID"


    def status_badge(self, obj):
        colors = {
            "pending": "gray",
            "processing": "orange",
            "completed": "green",
            "failed": "red",
        }
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(obj.status, "black"),
            obj.status.upper(),
        )
