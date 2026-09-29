"""DB-backed operations survive Redis restarts; secrets never enter job payloads."""
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from core.models import (OperationsPolicy, OperationJob, OperationalAlert, ServiceHealth, PriceRelease,
                         City, ImportBatch)
from core.source_engine import fetch_source_body, fetch_public, path_value


def policy():
    return OperationsPolicy.objects.get_or_create(pk=1)[0]


def weather_key(city, p):
    from core.studio_contract import digest
    return 'weather:'+digest({'city': city.pk, 'lat': str(city.latitude), 'lon': str(city.longitude), 'url': p.weather_url, 'path': p.weather_value_path, 'condition': p.weather_condition_path, 'unit': p.weather_unit, 'ttl': p.weather_seconds, 'integration': p.weather_integration_id, 'credentials_revision': str(p.weather_integration.updated_at) if p.weather_integration_id else None})


def weather_value(city):
    if city is None or not city.active:
        return {'status': 'unavailable', 'value': None}
    p = policy()
    value = cache.get(weather_key(city, p))
    if value and value['expires_at'] > timezone.now().isoformat():
        return value
    return {'status': 'unavailable', 'value': None, 'city': str(city)}


def refresh_weather():
    p = policy()
    if not p.weather_url or not p.weather_integration_id or not p.weather_integration.is_active:
        return
    for city in City.objects.filter(active=True, displaypreference__isnull=False).distinct():
        key = weather_key(city, p)
        if cache.get(key):
            continue
        try:
            url = p.weather_url.replace('{lat}', str(city.latitude)).replace('{lon}', str(city.longitude))
            raw = fetch_source_body(url, p.weather_integration.key, None)
            data = json.loads(raw)
            now = timezone.now()
            value = {'status': 'fresh', 'value': path_value(data, p.weather_value_path),
                     'condition': path_value(data, p.weather_condition_path) if p.weather_condition_path else '',
                     'city': str(city), 'unit': p.weather_unit, 'updated_at': now.isoformat(),
                     'expires_at': (now+timedelta(seconds=p.weather_seconds)).isoformat()}
            cache.set(key, value, p.weather_seconds)
        except Exception:
            set_alert(f'weather-{city.pk}', True, 'دریافت آب‌وهوا ناموفق است.')
        else:
            set_alert(f'weather-{city.pk}', False, '')


def enqueue_backup(actor):
    import uuid
    job = OperationJob.objects.create(kind='backup', key='manual-backup:'+str(uuid.uuid4()), payload={'actor_id': actor.pk}, next_attempt=timezone.now())
    return job


@transaction.atomic
def schedule_backup():
    config = OperationsPolicy.objects.select_for_update().get_or_create(pk=1)[0]
    now = timezone.now()
    if config.backup_enabled and (not config.next_backup or config.next_backup <= now):
        slot = config.next_backup or now
        OperationJob.objects.get_or_create(key='backup:'+slot.isoformat(), defaults={'kind': 'backup', 'next_attempt': now})
        config.next_backup = now+timedelta(hours=config.backup_hours)
        config.save(update_fields=['next_backup'])


def backup_root():
    root = Path(getattr(settings, 'GADGET_BACKUP_DIR', settings.BASE_DIR/'runtime'/'backups'))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def make_backup(job):
    root = backup_root()
    final = root/(str(job.pk)+'.tar.gz')
    if final.exists():
        return final.name
    with tempfile.TemporaryDirectory(dir=root) as folder:
        folder = Path(folder)
        database = folder/'database.dump'
        if connection.vendor == 'postgresql':
            db = settings.DATABASES['default']
            env = os.environ.copy()
            env.update({'PGPASSWORD': str(db.get('PASSWORD', '')), 'PGHOST': str(db.get('HOST', '')), 'PGPORT': str(db.get('PORT', 5432)), 'PGUSER': str(db.get('USER', ''))})
            subprocess.run(['pg_dump', '--format=custom', '--file', str(database), str(db['NAME'])], env=env, capture_output=True, check=True, timeout=1200)
        elif connection.vendor == 'sqlite':
            import sqlite3
            connection.ensure_connection()
            with sqlite3.connect(database) as destination:
                connection.connection.backup(destination)
        else:
            raise ValidationError('نوع دیتابیس برای پشتیبان‌گیری پشتیبانی نمی‌شود.')
        # Recovery keys are bundled in this private archive; never return them in the UI or logs.
        keys = folder/'recovery-settings.json'
        keys.write_text(json.dumps({'django_secret_key': settings.SECRET_KEY, 'gadget_master_key': settings.GADGET_MASTER_KEY, 'database_engine': connection.vendor}))
        os.chmod(keys, 0o600)
        output = folder/'backup.tar.gz'
        runtime = Path(os.environ.get('GADGET_STATE_DIR', settings.BASE_DIR/'runtime'))
        with tarfile.open(output, 'w:gz') as archive:
            archive.add(database, arcname='database.dump')
            archive.add(keys, arcname='recovery-settings.json')
            if runtime.exists():
                for name in ['master.key', 'django.key']:
                    file = runtime/name
                    if file.is_file():
                        archive.add(file, arcname='runtime/'+name)
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                def safe_member(member):
                    return member if member.isfile() or member.isdir() else None
                archive.add(media, arcname='media', filter=safe_member)
        os.chmod(output, 0o600)
        os.replace(output, final)
    return final.name


def send_sms(job):
    p = policy()
    integration = p.sms_integration
    if not p.sms_enabled or not integration or not integration.is_active:
        raise ValidationError('اتصال پیامک فعال نیست.')
    parts = urlsplit(integration.endpoint)
    if parts.scheme != 'https':
        raise ValidationError('پیامک نیازمند HTTPS است.')
    if integration.options.get('auth_location') == 'query':
        raise ValidationError('در اتصال پیامکی، احراز هویت را به روش هدر تنظیم کنید.')
    header = integration.options.get('auth_header', 'Authorization')
    scheme = integration.options.get('auth_scheme', 'Bearer' if header == 'Authorization' else '')
    headers = {'Content-Type': 'application/json', 'Idempotency-Key': job.key,
               header: (scheme+' ' if scheme else '')+integration.secret()}
    text = p.sms_template.replace('{service}', job.payload['service']).replace('{state}', job.payload['state'])
    payload = {p.sms_recipient_key: p.sms_recipient, p.sms_message_key: text}
    fetch_public(integration.endpoint, headers, method='POST', body=json.dumps(payload).encode())
    return 'provider_http_accepted'


@transaction.atomic
def set_alert(service, active, message):
    alert, _ = OperationalAlert.objects.select_for_update().get_or_create(service=service)
    if alert.active == active:
        return
    alert.active = active
    alert.generation += 1
    alert.message = message
    alert.save()
    p = policy()
    if p.sms_enabled:
        OperationJob.objects.get_or_create(key=f'alert:{service}:{alert.generation}', defaults={'kind': 'sms', 'payload': {'service': service, 'state': 'خطا' if active else 'بازیابی'}, 'next_attempt': timezone.now()})


def evaluate_alerts():
    for health in ServiceHealth.objects.all():
        if health.status == 'disabled':
            continue
        failed = health.status == 'down' or health.last_check_at < timezone.now()-timedelta(minutes=35 if health.service_name == 'backups' else 5)
        set_alert(health.service_name, failed, 'سرویس در دسترس نیست یا گزارش آن قدیمی است.' if failed else '')
    disk = shutil.disk_usage(backup_root())
    set_alert('disk', disk.free/disk.total < .1, 'فضای آزاد ذخیره‌سازی کمتر از ۱۰ درصد است.')
    set_alert('operations-queue', OperationJob.objects.filter(status='failed').exists(), 'کار اجرایی ناموفق وجود دارد.')


def process_jobs(limit=5, kind=None):
    now = timezone.now()
    query = OperationJob.objects.filter(Q(status='pending', next_attempt__lte=now) | Q(status='running', lease_until__lt=now))
    if kind:
        query = query.filter(kind=kind)
    ids = list(query.order_by('created_at').values_list('pk', flat=True)[:limit])
    for pk in ids:
        with transaction.atomic():
            job = OperationJob.objects.select_for_update().get(pk=pk)
            if job.status in ['done', 'failed'] or job.status == 'running' and job.lease_until >= now or job.status == 'pending' and job.next_attempt > now:
                continue
            job.status = 'running'
            job.lease_until = now+timedelta(minutes=30)
            job.attempts += 1
            job.save()
        try:
            result = make_backup(job) if job.kind == 'backup' else send_sms(job)
        except Exception:
            OperationJob.objects.filter(pk=pk).update(status='failed' if job.attempts >= 5 else 'pending', next_attempt=timezone.now()+timedelta(seconds=min(3600, 30*2**job.attempts)), result='اجرا ناموفق؛ اتصال، فضای ذخیره‌سازی و تنظیمات سرویس را بررسی کنید.')
        else:
            OperationJob.objects.filter(pk=pk).update(status='done', result=result, completed_at=timezone.now())


def publish_due_prices():
    from core.price_versions import activate_due_release
    for pk in PriceRelease.objects.filter(cancelled=False, published_at__isnull=True, scheduled_at__lte=timezone.now()).order_by('scheduled_at', 'number').values_list('pk', flat=True):
        activate_due_release(pk)


def tick():
    publish_due_prices()
    ImportBatch.objects.filter(expires_at__lte=timezone.now()).delete()  # Disposable preview rows only.
    schedule_backup()
    evaluate_alerts()
    process_jobs(kind='sms')
