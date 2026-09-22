from celery import shared_task
from django.utils import timezone

from core.monitoring import check_services, mark_stale_devices_offline
from core.mqtt import publish_device_message
from core.models import MessageCampaign
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
    return run_wordpress_pull_sync()


@shared_task(autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def publish_device_config_changed(external_id: str, ui_version: int) -> None:
    """Prompt a device to retrieve its latest signed configuration."""
    publish_device_message(
        external_id=external_id,
        suffix="commands/config",
        payload={"type": "config.changed", "ui_version": ui_version},
    )


@shared_task(autoretry_for=(OSError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def dispatch_due_message_campaigns() -> int:
    """Publish due company messages to their explicitly selected devices."""
    campaigns = MessageCampaign.objects.filter(
        status=MessageCampaign.Status.SCHEDULED,
        scheduled_at__lte=timezone.now(),
    ).prefetch_related("target_devices")
    sent_count = 0
    for campaign in campaigns:
        for device in campaign.target_devices.filter(is_active=True):
            publish_device_message(
                external_id=device.external_id,
                suffix="commands/message",
                payload={
                    "type": "message.campaign",
                    "campaign_id": campaign.id,
                    "title": campaign.name,
                    "message": campaign.message,
                },
            )
        campaign.status = MessageCampaign.Status.SENT
        campaign.save(update_fields=["status", "updated_at"])
        sent_count += 1
    return sent_count
