import fcntl
import os
import time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import ServiceHealth
from core.studio_operations import tick, process_jobs


class Command(BaseCommand):
    help = 'Independent DB-backed backup, price publication and notification worker.'
    def add_arguments(self, parser):
        parser.add_argument('--backups', action='store_true', help='Run slow backups separately from scheduling and alerts.')

    def handle(self, *args, **options):
        service = 'backups' if options['backups'] else 'operations'
        root = Path(os.environ.get('GADGET_STATE_DIR', settings.BASE_DIR/'runtime'))
        root.mkdir(parents=True, exist_ok=True)
        with (root/(service+'.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            while True:
                try:
                    process_jobs(limit=1, kind='backup') if options['backups'] else tick()
                    ServiceHealth.objects.update_or_create(service_name=service, defaults={'status': 'up', 'last_check_at': timezone.now()})
                except Exception as exc:
                    self.stderr.write(type(exc).__name__ + ': operations cycle failed')
                time.sleep(10)
