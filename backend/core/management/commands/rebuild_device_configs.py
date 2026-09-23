from django.core.management.base import BaseCommand

from core.config_sync import refresh_all_device_configs


class Command(BaseCommand):
    help = "Rebuild existing device configurations after deployment or bulk imports."

    def handle(self, *args, **options):
        refresh_all_device_configs()
        self.stdout.write(self.style.SUCCESS("Device configurations rebuilt."))
