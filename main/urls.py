from django.urls import path, include

from .views import (
    video_dashboard,
    video_metadata_api,
    category_list_api,
    video_frames_api,
)

app_name = "main"

urlpatterns = [
    path("", video_dashboard, name="video-dashboard"),
    path(
        "api/v1/",
        include(
            [
                path("videos/", video_metadata_api),
                path("categories/", category_list_api),
                path("video-frames/", video_frames_api),
            ]
        ),
    ),
]
