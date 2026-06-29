from django.db import models


class VideoCategory(models.Model):

    id = models.AutoField(primary_key=True)

    name = models.CharField(
        max_length=200,
        unique=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "video_category"
        ordering = ["id"]

    def __str__(self):
        return self.name


class Video(models.Model):

    id = models.BigAutoField(primary_key=True)

    video_url = models.CharField(
        max_length=500,
        unique=True,
        db_index=True,
    )

    title = models.CharField(max_length=300, db_index=True)

    category = models.ForeignKey(
        VideoCategory,
        on_delete=models.PROTECT,
        related_name="videos",
        db_index=True,
    )

    uploaded_date = models.DateField(null=True, blank=True, db_index=True)

    extra_metadata = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video"
        ordering = ["-uploaded_date", "-id"]
        indexes = [
            models.Index(fields=["category", "uploaded_date"]),
            models.Index(fields=["category", "uploaded_date", "id"]),
            models.Index(fields=["uploaded_date", "id"]),
        ]

    def __str__(self):
        return self.title or f"Video {self.id}"


class VideoTechnicalMetadata(models.Model):

    ORIENTATION_CHOICES = [
        ("landscape", "Landscape"),
        ("portrait", "Portrait"),
    ]

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="tech",
        primary_key=True,
    )

    resolution = models.CharField(max_length=50, null=True, blank=True)

    orientation = models.CharField(
        max_length=20,
        choices=ORIENTATION_CHOICES,
        null=True,
        blank=True,
        db_index=True,
    )

    duration_ms = models.BigIntegerField(null=True, blank=True, db_index=True)

    fps = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )

    bitrate = models.BigIntegerField(null=True, blank=True)

    video_codec = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    audio_codec = models.CharField(max_length=100, null=True, blank=True, db_index=True)

    audio_channels = models.PositiveSmallIntegerField(null=True, blank=True)

    file_size = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "video_technical_metadata"
        indexes = [
            models.Index(fields=["orientation", "duration_ms"]),
            models.Index(fields=["video_codec", "audio_codec"]),
        ]

    def __str__(self):
        return f"TechMeta: Video {self.video_id}"


class VideoExtendedMetadata(models.Model):

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="extended",
        primary_key=True,
    )

    frame_count = models.BigIntegerField(null=True, blank=True)

    pixel_format = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    bit_depth = models.PositiveSmallIntegerField(null=True, blank=True)

    container_format = models.CharField(
        max_length=50, null=True, blank=True, db_index=True
    )

    audio_sample_rate = models.PositiveIntegerField(null=True, blank=True)

    audio_bitrate = models.BigIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "video_extended_metadata"
        indexes = [
            models.Index(fields=["container_format", "audio_bitrate"]),
        ]

    def __str__(self):
        return f"ExtMeta: Video {self.video_id}"


class VideoFrame(models.Model):

    FRAME_TYPE_CHOICES = [
        ("key", "Key Frame"),
        ("thumb", "Thumbnail"),
    ]

    id = models.BigAutoField(primary_key=True)

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="frames",
        db_index=True,
    )

    frame_s3_key = models.CharField(max_length=700, unique=True)

    frame_number = models.PositiveIntegerField()

    timestamp_ms = models.FloatField(null=True, blank=True)

    frame_type = models.CharField(
        max_length=20,
        choices=FRAME_TYPE_CHOICES,
        default="key",
        db_index=True,
    )

    thumbnail_score = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "video_frame"
        ordering = ["video_id", "frame_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["video", "frame_number"],
                name="unique_frame_per_video",
            )
        ]
        indexes = [
            models.Index(fields=["video", "frame_number"]),
            models.Index(fields=["video", "frame_type"]),
            models.Index(fields=["video", "frame_type", "frame_number"]),
        ]

    def __str__(self):
        return f"{self.video_id}-{self.frame_number}"


class VideoProcessingState(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        related_name="processing",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    metadata_extracted = models.BooleanField(default=False)
    frames_extracted = models.BooleanField(default=False)
    thumbnails_generated = models.BooleanField(default=False)

    last_error = models.TextField(null=True, blank=True)

    retry_count = models.PositiveSmallIntegerField(default=0, db_index=True)

    last_processed_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_processing_state"
        indexes = [
            models.Index(fields=["status", "retry_count"]),
            models.Index(fields=["status", "updated_at"]),
        ]

    def __str__(self):
        return f"Processing: Video {self.video_id} ({self.status})"
