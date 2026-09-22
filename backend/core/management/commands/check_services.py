from django.core.management.base import BaseCommand

from core.monitoring import check_services


class Command(BaseCommand):
    help = "Probe the API, database, Redis, MQTT, and Celery worker, then store their health states."

    def handle(self, *args, **options):
        results = check_services()
        for result in results:
            self.stdout.write(
                f"{result.service_name}: {result.status} ({result.response_time_ms} ms)"
            )
