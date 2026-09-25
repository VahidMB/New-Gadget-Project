"""Evaluate user rules on valid content; retain alert audit history permanently."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import hashlib

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from core.models import BuzzerRule, BuzzerEvent
from core.runtime import platform_settings


def number(value):
    try:
        text = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace(",", "").replace("٬", "").replace("٫", ".").strip()
        result = Decimal(text)
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def quiet(rule, now):
    local = now.astimezone(ZoneInfo(platform_settings().timezone))
    if rule.weekdays and local.weekday() not in rule.weekdays:
        return True
    if not rule.quiet_start or not rule.quiet_end:
        return False
    time = local.time().replace(tzinfo=None)
    if rule.quiet_start < rule.quiet_end:
        return rule.quiet_start <= time < rule.quiet_end
    return time >= rule.quiet_start or time < rule.quiet_end


def values(content):
    result = []
    for source in content["sources"]:
        if source["data"]:
            result.append((f"source:{source['id']}", source["data"]["value"], source["data"]["expires_at"]))
    for prices in content["price_lists"]:
        for item in prices["items"]:
            if item["amount"] is not None:
                result.append((f"price:{prices['id']}:{item['code']}", item["amount"], item["valid_until"]))
    for message in content["messages"]:
        result.append((f"message:{message['id']}", message["message"], message["expires_at"].isoformat()))
    return result


def evaluate_device(device, content=None):
    from core.content import device_content
    if not device.is_active or not device.customer_enabled or device.provisioning_state != "provisioned" or (device.company and not device.company.is_active) or (device.assigned_user and not device.assigned_user.is_active):
        return 0
    content = content or device_content(device)
    now = timezone.now()
    count = 0
    for rule_id in device.buzzer_rules.filter(enabled=True).values_list("pk", flat=True):
        with transaction.atomic():
            rule = BuzzerRule.objects.select_for_update().get(pk=rule_id)
            initialized_key = f"buzzer-initialized:{rule.pk}:{rule.updated_at.isoformat()}"
            initialized = cache.get(initialized_key, False)
            for key, value, expires in values(content):
                if rule.scope == "source" and key != f"source:{rule.source_id}":
                    continue
                if rule.scope == "price" and (not rule.price_item_id or key != f"price:{rule.price_item.price_list_id}:{rule.price_item.code}"):
                    continue
                if rule.scope == "messages" and not key.startswith("message:"):
                    continue
                state_key = f"buzzer-state:{rule.pk}:{rule.updated_at.isoformat()}:{key}"
                previous = cache.get(state_key)
                if previous and previous.get("expires", "") <= now.isoformat():
                    previous = None
                digest = hashlib.sha256(str(value).encode()).hexdigest()
                current = number(value)
                anchor = previous.get("anchor") if previous else None
                anchor_at = previous.get("anchor_at", now.timestamp()) if previous else now.timestamp()
                old = number(anchor if rule.window_seconds else previous.get("number")) if previous else None
                if rule.window_seconds and now.timestamp()-anchor_at > rule.window_seconds:
                    previous = None
                    old = None
                triggered = False
                if not previous:
                    anchor, anchor_at = str(current) if current is not None else None, now.timestamp()
                    triggered = (rule.notify_first or initialized) and rule.trigger == "new"
                elif digest != previous["digest"]:
                    if rule.trigger == "new":
                        triggered = True
                    elif old is not None and current is not None and rule.threshold is not None:
                        change = current-old
                        direction_ok = rule.direction == "both" or (rule.direction == "up" and change > 0) or (rule.direction == "down" and change < 0)
                        if rule.trigger == "percent" and old != 0:
                            triggered = direction_ok and abs(change/old)*100 >= rule.threshold
                        elif rule.trigger == "absolute":
                            triggered = direction_ok and abs(change) >= rule.threshold
                        elif rule.trigger == "above":
                            triggered = number(previous["number"]) is not None and number(previous["number"]) < rule.threshold <= current
                        elif rule.trigger == "below":
                            triggered = number(previous["number"]) is not None and number(previous["number"]) > rule.threshold >= current
                cache.set(state_key, {"digest": digest, "number": str(current) if current is not None else None, "anchor": anchor, "anchor_at": anchor_at, "expires": expires}, max(300, rule.window_seconds*2))
                if not triggered or quiet(rule, now):
                    continue
                if rule.last_triggered_at and (now-rule.last_triggered_at).total_seconds() < rule.cooldown_seconds:
                    continue
                if BuzzerEvent.objects.filter(rule=rule, created_at__gte=now-timedelta(hours=1)).count() >= rule.max_per_hour:
                    continue
                from django.utils.dateparse import parse_datetime
                deadline = min(now+timedelta(seconds=30), parse_datetime(expires))
                if deadline <= now:
                    continue
                BuzzerEvent.objects.create(device=device, rule=rule, reason=rule.name, item_key=key, expires_at=deadline, payload={"duration_ms": rule.duration_ms, "repeat": rule.repeat, "gap_ms": rule.gap_ms, "trigger": rule.trigger, "threshold": str(rule.threshold) if rule.threshold is not None else None, "reference": str(old) if old is not None else None, "current": str(current) if current is not None else None})
                rule.last_triggered_at = now
                rule.save(update_fields=["last_triggered_at"])
                count += 1
            cache.set(initialized_key, True, 86400)
    return count


def rules_config(device):
    result = []
    for rule in device.buzzer_rules.filter(enabled=True):
        result.append({"id": rule.pk, "name": rule.name, "scope": rule.scope, "source_id": rule.source_id, "price_item_id": rule.price_item_id, "trigger": rule.trigger, "direction": rule.direction, "threshold": str(rule.threshold) if rule.threshold is not None else None, "window_seconds": rule.window_seconds, "notify_first": rule.notify_first, "duration_ms": rule.duration_ms, "repeat": rule.repeat, "gap_ms": rule.gap_ms, "cooldown_seconds": rule.cooldown_seconds, "max_per_hour": rule.max_per_hour, "quiet_start": rule.quiet_start.isoformat() if rule.quiet_start else None, "quiet_end": rule.quiet_end.isoformat() if rule.quiet_end else None, "weekdays": rule.weekdays})
    return {"mode": "server_events", "timezone": platform_settings().timezone, "deduplicate_by": "event_id", "discard_expired": True, "rules": result}


def pending_events(device):
    return [{"event_id": str(event.pk), "type": "buzzer.alert", "rule_id": event.rule_id, "expires_at": event.expires_at.isoformat(), **event.payload} for event in device.buzzer_events.filter(expires_at__gt=timezone.now(), acknowledged_at__isnull=True, rule__enabled=True)]


def notify_source(source_id):
    """Push ingestion wakes processing immediately; periodic jobs also provide recovery."""
    from core.tasks import process_live_source
    try:
        process_live_source.apply_async(args=[source_id], retry=False)
    except Exception:
        pass  # Persistent source metadata and cache are rechecked by the regular worker task.
