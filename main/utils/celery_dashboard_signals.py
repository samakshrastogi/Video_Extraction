from celery.signals import task_prerun, task_postrun, task_failure
from rich.live import Live
import threading
import time

from main.utils.global_terminal_dashboard import dashboard

_live = None
_started = False


def start_dashboard():
    global _live, _started

    if _started:
        return

    _started = True

    def run():
        global _live
        with Live(dashboard.render(), refresh_per_second=2) as live:
            _live = live
            while True:
                live.update(dashboard.render())
                time.sleep(1)

    t = threading.Thread(target=run, daemon=True)
    t.start()


# ===== TASK START =====
@task_prerun.connect
def task_prerun_handler(task_id=None, task=None, **kwargs):
    start_dashboard()
    dashboard.task_started(task_id, task.name)
    dashboard.queue_stats["processing"] += 1


# ===== TASK END =====
@task_postrun.connect
def task_postrun_handler(task_id=None, task=None, state=None, **kwargs):
    status = "SUCCESS" if state == "SUCCESS" else state
    dashboard.task_finished(task_id, status)


# ===== TASK FAIL =====
@task_failure.connect
def task_failure_handler(task_id=None, task=None, **kwargs):
    dashboard.task_finished(task_id, "FAILED")
