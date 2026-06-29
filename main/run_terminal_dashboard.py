from rich.live import Live
import time
from main.utils.global_terminal_dashboard import dashboard
import sys
sys.stdout.reconfigure(encoding='utf-8')


print("🚀 Terminal Dashboard Started")

with Live(dashboard.render(), refresh_per_second=2, screen=True) as live:
    while True:
        live.update(dashboard.render())
        time.sleep(1)
