import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "video_extraction.settings")

app = Celery("video_extraction")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ===== SAFETY DEFAULTS (ONLY IF NOT PROVIDED) =====
app.conf.update(
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

# ===== TIMEZONE =====
app.conf.timezone = os.getenv("TIME_ZONE", "UTC")

# ===== WINDOWS SAFE =====
if os.name == "nt":
    app.conf.worker_pool = os.getenv("CELERY_POOL", "solo")

# ===== FUTURE SCALING READY =====
app.conf.task_routes = {
    # Example:
    # "main.tasks.process_video_task": {"queue": "video_processing"},
}
# ===== ULTRA TERMINAL DASHBOARD SIGNALS =====
try:
    import main.utils.celery_dashboard_signals
except Exception as e:
    print(f"[Dashboard Signals Disabled] {e}")
