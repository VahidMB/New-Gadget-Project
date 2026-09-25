from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from core.models import (ExternalDataSource, MessageCampaign, CampaignDelivery)
from core.access import account_rule, rule_for, company_tree_ids
from core.runtime import platform_settings
from core.source_engine import refresh_source
from core.content import purge_expired_content
from core.mqtt import publish_device_message


@shared_task
def refresh_sources():
    refreshed = 0
    now = timezone.now()
    for source in ExternalDataSource.objects.filter(is_active=True, update_mode="periodic").exclude(source_type__in=["telegram", "internal"]).select_related("company").iterator():
        interval = source.refresh_interval_seconds
        if source.company:
            rule = account_rule(source.company)
            if not rule.can_add_sources:
                continue
            interval = max(interval, rule.min_refresh_seconds)
        if source.last_attempt_at and (now-source.last_attempt_at).total_seconds() < interval:
            continue
        # TTL lock prevents overlapping worker fetches without persisting raw data.
        lock = f"source-fetch:{source.pk}"
        if not cache.add(lock, True, 30):
            continue
        try:
            refreshed += int(refresh_source(source))
        finally:
            cache.delete(lock)
    return refreshed


@shared_task
def expire_content():
    # Audit, sync, alert and delivery logs are permanent. Only opted-in transient values expire.
    if not platform_settings().cleanup_enabled:
        return 0
    from django.contrib.sessions.models import Session
    expired_sessions, _ = Session.objects.filter(expire_date__lte=timezone.now()).delete()
    return purge_expired_content() + expired_sessions


@shared_task
def dispatch_campaigns():
    now = timezone.now()
    sent = 0
    ids = MessageCampaign.objects.filter(status="scheduled", scheduled_at__lte=now, expires_at__gt=now).values_list("pk", flat=True)
    for pk in ids:
        with transaction.atomic():
            campaign = MessageCampaign.objects.select_for_update().select_related("company").get(pk=pk)
            if campaign.status != "scheduled":
                continue
            if not campaign.company.is_active or not account_rule(campaign.company).can_send_messages:
                campaign.last_error = "حساب غیرفعال است یا مجوز ارسال Pro ندارد."
                campaign.save(update_fields=["last_error"])
                continue
            blocked = False
            for device in campaign.target_devices.select_related("company", "assigned_user").all():
                if device.company_id not in company_tree_ids(campaign.company_id) or not device.is_active or not device.customer_enabled or device.provisioning_state != "provisioned" or not rule_for(device.normalized_plan).can_send_messages or (device.assigned_user and not device.assigned_user.is_active):
                    blocked = True
                    continue
                delivery, _ = CampaignDelivery.objects.get_or_create(campaign=campaign, device=device)
                if delivery.delivered_at:
                    continue
                delivery.attempts += 1
                try:
                    publish_device_message(external_id=device.external_id, suffix="commands/message", retain=False, payload={"type": "message.campaign", "campaign_id": campaign.pk, "title": campaign.name, "message": campaign.message, "price_list_id": campaign.price_list_id, "expires_at": campaign.expires_at.isoformat()})
                    if campaign.price_list_id and campaign.price_list.company_id == campaign.company_id:
                        campaign.price_list.target_devices.add(device)
                    delivery.delivered_at = timezone.now()
                    delivery.last_error = ""
                except Exception:
                    delivery.last_error = "انتشار پیام ناموفق بود؛ تلاش مجدد انجام می‌شود."
                    blocked = True
                delivery.save()
            if not blocked:
                campaign.status = "sent"
                campaign.last_error = ""
                sent += 1
            else:
                campaign.last_error = "برخی مقاصد قابل ارسال نیستند؛ وضعیت دستگاه و اتصال را بررسی کنید."
            campaign.save(update_fields=["status", "last_error", "updated_at"])
    return sent


@shared_task
def publish_content_hints():
    """Notify provisioned devices when current content changes; devices re-fetch over HTTPS."""
    import hashlib
    import json
    from core.models import WordPressDevice
    from core.content import device_content
    published = 0
    for device in WordPressDevice.objects.filter(is_active=True, customer_enabled=True, provisioning_state="provisioned", company__is_active=True).select_related("assigned_user"):
        if device.assigned_user and not device.assigned_user.is_active:
            continue
        data = device_content(device)
        if not data["live_updates"]:
            continue
        data.pop("server_time", None)
        revision = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        key = f"content-notified:{device.pk}"
        if cache.get(key) == revision:
            continue
        try:
            publish_device_message(external_id=device.external_id, suffix="events/content", retain=False, payload={"type": "content.changed", "revision": revision, "fetch_path": f"/api/v1/devices/{device.external_id}/content/"})
        except Exception:
            continue  # The next run retries; current values still have explicit TTLs.
        cache.set(key, revision, 86400)
        published += 1
    return published


@shared_task
def process_buzzer_rules():
    from core.models import WordPressDevice
    from core.buzzer import evaluate_device
    for device in WordPressDevice.objects.filter(buzzer_rules__enabled=True, is_active=True, customer_enabled=True, provisioning_state="provisioned").distinct().select_related("company", "assigned_user"):
        evaluate_device(device)
    return publish_buzzer_events()


@shared_task
def publish_buzzer_events():
    from core.models import BuzzerEvent
    count = 0
    for event in BuzzerEvent.objects.filter(expires_at__gt=timezone.now(), published_at__isnull=True, acknowledged_at__isnull=True, rule__enabled=True).select_related("device", "device__company", "device__assigned_user"):
        device = event.device
        if not device.is_active or not device.customer_enabled or device.provisioning_state != "provisioned" or (device.company and not device.company.is_active) or (device.assigned_user and not device.assigned_user.is_active):
            continue
        try:
            publish_device_message(external_id=device.external_id, suffix="events/buzzer", retain=False, payload={"type": "buzzer.alert", "event_id": str(event.pk), "rule_id": event.rule_id, "expires_at": event.expires_at.isoformat(), **event.payload})
        except Exception:
            continue
        event.published_at = timezone.now()
        event.save(update_fields=["published_at"])
        count += 1
    return count
