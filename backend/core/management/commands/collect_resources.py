import time
from django.core.management.base import BaseCommand
from core.resources import collect_local_resources


class Command(BaseCommand):
    help = "Read CPU/RAM from visible service processes; optionally run continuously."
    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
    def handle(self, *args, **options):
        while True:
            count = collect_local_resources()
            self.stdout.write(f"Updated {count} service resource snapshots")
            if not options["loop"]:
                break
            time.sleep(30)
