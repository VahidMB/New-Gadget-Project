from django.core.management.base import BaseCommand

from core.monitoring import mark_stale_devices_offline


class Command(BaseCommand):
    help = "Mark devices with stale heartbeats as offline."

    def handle(self, *args, **options):
        count = mark_stale_devices_offline()
        self.stdout.write(f"Marked {count} stale device(s) offline.")