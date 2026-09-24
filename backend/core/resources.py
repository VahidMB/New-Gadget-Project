"""Read-only collector: current per-service CPU/RAM/network/disk snapshots."""
from collections import defaultdict
import time
import psutil
from core.models import ResourceSnapshot


def collect_local_resources():
    groups = defaultdict(list)
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = process.info["name"] or ""
            command = " ".join(process.info["cmdline"] or [])
            service = None
            if name.startswith("postgres"):
                service = "db"
            elif "redis-server" in name:
                service = "redis"
            elif "mosquitto" in name:
                service = "mqtt"
            elif "celery" in command:
                service = "beat" if " beat " in " " + command + " " else "worker"
            elif "gunicorn" in command or "manage.py runserver" in command:
                service = "api"
            if service:
                process.cpu_percent(None)
                groups[service].append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.15)
    for service, processes in groups.items():
        cpu = memory = 0
        for process in processes:
            try:
                cpu += process.cpu_percent(None)
                memory += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        ResourceSnapshot.objects.update_or_create(service=service, defaults={"cpu_percent": cpu, "memory_bytes": memory, "origin": "process collector"})
    return len(groups)
