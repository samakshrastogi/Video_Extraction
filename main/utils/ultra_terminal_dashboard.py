from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from datetime import datetime
import psutil
import time

console = Console()


class UltraTerminalDashboard:

    def __init__(self):
        self.start_time = datetime.now()
        self.active_tasks = {}
        self.history = []
        self.queue_stats = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
        }

    # ---------------- TASK CONTROL ---------------- #

    def task_started(self, task_id, name):
        self.active_tasks[task_id] = {
            "name": name,
            "start": time.time(),
        }

    def task_finished(self, task_id, status="SUCCESS"):
        if task_id not in self.active_tasks:
            return

        task = self.active_tasks.pop(task_id)
        duration = time.time() - task["start"]

        self.queue_stats["processing"] = max(0, self.queue_stats["processing"] - 1)

        if status == "SUCCESS":
            self.queue_stats["completed"] += 1
        else:
            self.queue_stats["failed"] += 1

        self.history.append(
            (
                datetime.now().strftime("%H:%M:%S"),
                task["name"],
                status,
                f"{duration:.2f}s",
            )
        )

    # ---------------- UI BUILD ---------------- #

    def build_header(self):
        uptime = datetime.now() - self.start_time

        return Panel(
            f"Worker : celery@worker\n"
            f"Uptime : {str(uptime).split('.')[0]}\n"
            f"Active Tasks : {len(self.active_tasks)}",
            title="VIDEO PROCESSING SYSTEM",
            border_style="cyan",
        )

    def build_queue_panel(self):
        q = self.queue_stats
        return Panel(
            f"Pending    : {q['pending']}\n"
            f"Processing : {q['processing']}\n"
            f"Completed  : {q['completed']}\n"
            f"Failed     : {q['failed']}",
            title="Queue Stats",
            border_style="magenta",
        )

    def build_active_table(self):
        table = Table(title="Active Tasks")
        table.add_column("Task")
        table.add_column("Runtime")

        for t in self.active_tasks.values():
            runtime = time.time() - t["start"]
            table.add_row(
                t["name"],
                f"{runtime:.1f}s",
            )

        return table

    def build_history_table(self):
        table = Table(title="Recent Activity")
        table.add_column("Time")
        table.add_column("Task")
        table.add_column("Status")
        table.add_column("Duration")

        for h in self.history[-10:]:
            table.add_row(*h)

        return table

    def build_system_panel(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent

        return Panel(
            f"CPU : {cpu}%\nMemory : {mem}%",
            title="System",
            border_style="yellow",
        )

    # ---------------- RENDER ---------------- #

    def render(self):
        layout = Layout()

        layout.split_column(
            Layout(self.build_header(), size=5),
            Layout(name="main"),
        )

        layout["main"].split_row(
            Layout(self.build_queue_panel(), size=30),
            Layout(name="tables"),
            Layout(self.build_system_panel(), size=25),
        )

        layout["tables"].split_column(
            Layout(self.build_active_table(), size=10),
            Layout(self.build_history_table()),
        )

        return layout
