from celery import shared_task
from django.db import transaction

from core.monitoring import check_services, mark_stale_devices_offline
from core.mqtt import publish_device_message
from core.models import WordPressDevice
from core.services import run_wordpress_pull_sync


@shared_task
def check_service_health() -> list[dict[str, str | int]]:
    """Persist a fresh health snapshot for each platform dependency."""
    return [
        {
            "service_name": result.service_name,
            "status": result.status,
            "response_time_ms": result.response_time_ms,
        }
        for result in check_services()
    ]


@shared_task
def mark_stale_devices() -> int:
    """Mark devices that stopped sending heartbeats as offline."""
    return mark_stale_devices_offline()


@shared_task(autoretry_for=(OSError, ValueError), retry_backoff=True, retry_kwargs={"max_retries": 3})
def wordpress_pull_sync() -> dict:
    """Synchronize the WordPress mirror on a schedule, with bounded retries."""
    from core.runtime import runtime_setting, platform_settings
    from django.core.cache import cache
    if not runtime_setting("WORDPRESS_API_BASE_URL"):
        return {"skipped": True}
    if not cache.add("wordpress-poll-due", True, platform_settings().wordpress_poll_seconds):
        return {"skipped": True}
    return run_wordpress_pull_sync()


@shared_task(autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
@transaction.atomic
def publish_device_config_changed(external_id: str, ui_version: int) -> None:
    """Publish the latest committed revision; old queued tasks cannot roll it back."""
    device = WordPressDevice.objects.select_for_update().filter(
        external_id=external_id, is_active=True, customer_enabled=True, provisioning_state="provisioned", config_sync_pending=True
    ).first()
    if device is None:
        return
    ui_version = device.ui_version
    publish_device_message(
        external_id=external_id,
        suffix="commands/config",
        payload={"type": "config.changed", "ui_version": ui_version},
    )
    WordPressDevice.objects.filter(pk=device.pk, ui_version=ui_version).update(config_sync_pending=False)


@shared_task
def dispatch_due_message_campaigns() -> int:
    from core.platform_tasks import dispatch_campaigns
    return dispatch_campaigns()


@shared_task
def retry_pending_config_notifications() -> int:
    from core.config_sync import enqueue_config_notification

    devices = WordPressDevice.objects.filter(
        config_sync_pending=True, is_active=True, provisioning_state="provisioned"
    ).values_list("external_id", "ui_version")
    count = 0
    for external_id, ui_version in devices.iterator():
        enqueue_config_notification(external_id, ui_version)
        count += 1
    return count

from core import platform_tasks  # noqa: E402,F401


@shared_task
def process_live_source(source_id):
    from core.models import SourceSelection
    from core.buzzer import evaluate_device
    from core.platform_tasks import publish_buzzer_events, publish_content_hints
    ids = SourceSelection.objects.filter(source_id=source_id, enabled=True).values_list("device_id", flat=True)
    for device in WordPressDevice.objects.filter(pk__in=ids).select_related("company", "assigned_user"):
        evaluate_device(device)
    publish_buzzer_events()
    publish_content_hints()
