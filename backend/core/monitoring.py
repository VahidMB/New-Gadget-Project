"""Active infrastructure probes and persistent service-health snapshots."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from datetime import timedelta

from celery import current_app
from django.conf import settings
from django.db import connection
from django.db.models import F
from django.utils import timezone
from redis import Redis

from core.models import DeviceStatus, ServiceHealth, Integration
from core.runtime import runtime_setting

Probe = Callable[[], None]


def _probe_api() -> None:
    from urllib.request import urlopen, Request
    from urllib.parse import urlsplit
    from core.runtime import platform_settings
    host = urlsplit(platform_settings().public_base_url).hostname or "localhost"
    request = Request(getattr(settings, "INTERNAL_API_URL", "http://api:8000") + "/api/v1/ping/", headers={"Host": host})
    with urlopen(request, timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("API liveness failed")


def _probe_database() -> None:
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _probe_redis() -> None:
    Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()


def _probe_mqtt() -> None:
    with socket.create_connection((runtime_setting("MQTT_HOST"), runtime_setting("MQTT_PORT")), timeout=1):
        pass


def _probe_worker() -> None:
    replies = current_app.control.inspect(timeout=1).ping()
    if not replies:
        raise RuntimeError("No Celery worker responded to ping")


def _record_result(service_name: str, probe: Probe) -> ServiceHealth:
    started_at = time.monotonic()
    try:
        probe()
        service_status = "up"
        error_message = ""
    except Exception as exc:  # Each unavailable dependency must be recorded, not crash the check run.
        service_status = "down"
        error_message = type(exc).__name__ + ": probe failed"

    response_time_ms = round((time.monotonic() - started_at) * 1000)
    health, created = ServiceHealth.objects.get_or_create(
        service_name=service_name,
        defaults={
            "status": service_status,
            "response_time_ms": response_time_ms,
            "error_message": error_message,
            "check_count": 1,
            "failed_count": int(service_status == "down"),
        },
    )
    if created:
        return health

    ServiceHealth.objects.filter(pk=health.pk).update(
        status=service_status,
        response_time_ms=response_time_ms,
        error_message=error_message,
        last_check_at=timezone.now(),
        check_count=F("check_count") + 1,
        failed_count=F("failed_count") + int(service_status == "down"),
    )
    health.refresh_from_db()
    return health


def check_services() -> list[ServiceHealth]:
    """Probe every deployed dependency and persist a fresh status snapshot."""
    probes: tuple[tuple[str, Probe], ...] = (
        ("api", _probe_api),
        ("db", _probe_database),
        ("redis", _probe_redis),
        ("mqtt", _probe_mqtt),
        ("worker", _probe_worker),
    )
    results = [_record_result(service_name, probe) for service_name, probe in probes]
    for integration in Integration.objects.filter(is_active=True, kind__in=["wordpress", "telegram"]):
        if integration.kind == "wordpress" and integration.endpoint:
            from core.source_engine import fetch_public
            results.append(_record_result("wordpress", lambda: fetch_public(integration.endpoint)))
    return results


def mark_stale_devices_offline() -> int:
    """Mark online/updating devices offline once their heartbeat exceeds the configured age."""
    from core.runtime import platform_settings
    stale_before = timezone.now() - timedelta(seconds=platform_settings().heartbeat_timeout)
    return DeviceStatus.objects.filter(
        status__in=["online", "updating"],
        last_heartbeat_at__lt=stale_before,
    ).update(status="offline")
