import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from urllib import error, parse, request

from django.conf import settings
from django.utils import timezone as django_timezone

from core.models import (
    SyncEntityType,
    SyncEventStatus,
    SyncNotification,
    SyncSource,
    UITemplate,
    WordPressDataSource,
    WordPressDevice,
    WordPressSyncEvent,
)


SIMPLE_PLAN_FIXED_CONFIG: dict[str, Any] = {
    "ui_version": 1,
    "plan": "simple",
    "theme": {
        "name": "dark",
        "primary_color": "#00B7FF",
        "secondary_color": "#FFFFFF",
        "background_color": "#000000",
    },
    "screen": {
        "orientation": "portrait",
        "width": 320,
        "height": 480,
        "refresh_mode": "manual",
    },
    "customizable": False,
    "screens": [
        {"type": "branding", "enabled": True, "animation": "fade", "duration_ms": 2500},
        {"type": "clock", "enabled": True},
        {"type": "calendar", "enabled": True},
        {"type": "weather", "enabled": True},
        {
            "type": "market",
            "enabled": True,
            "assets": ["usd", "gold", "silver", "btc"],
        },
    ],
}


PRO_PLAN_BASE_CONFIG: dict[str, Any] = {
    "ui_version": 1,
    "plan": "pro",
    "theme": {
        "name": "dark",
        "primary_color": "#00B7FF",
        "secondary_color": "#FFFFFF",
        "background_color": "#000000",
    },
    "screen": {
        "orientation": "portrait",
        "width": 320,
        "height": 480,
        "refresh_mode": "manual",
    },
    "customizable": True,
    "screens": [
        {"type": "branding", "enabled": True, "animation": "fade", "duration_ms": 2500},
        {"type": "clock", "enabled": True},
    ],
}


def _normalize_plan(raw_plan: Any) -> str:
    plan = str(raw_plan or "").strip().lower()
    if plan in {"pro", "vip", "premium", "professional"}:
        return "pro"
    return "simple"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _extract_custom_config(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        payload.get("custom_config"),
        payload.get("display_config"),
        payload.get("config"),
    ]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        candidates.extend([metadata.get("custom_config"), metadata.get("display_config"), metadata.get("config")])

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _active_template_config(plan: str) -> dict[str, Any]:
    """Serialize the active database template into the device UI contract."""
    template = (
        UITemplate.objects.filter(plan_type=plan, is_active=True)
        .prefetch_related("pages__elements")
        .order_by("-updated_at", "-id")
        .first()
    )
    if template is None:
        return {}

    pages = []
    for page in template.pages.filter(is_active=True):
        elements = [
            {
                "type": element.element_type,
                "label": element.label,
                "source_key": element.source_key,
                "position": {"x": element.x, "y": element.y, "width": element.width, "height": element.height},
                "font_size": element.font_size,
                "color": element.color,
                "style": element.style,
                "z_index": element.z_index,
                "config": element.config,
            }
            for element in page.elements.filter(is_visible=True)
        ]
        pages.append(
            {
                "key": page.page_key,
                "type": page.page_type,
                "priority": page.priority,
                "refresh_interval_ms": page.refresh_interval_ms,
                "visible_when": page.visible_when,
                "elements": elements,
            }
        )
    return {
        "template": {"name": template.name, "version": template.version},
        "theme": template.default_theme,
        "screen": template.default_screen,
        "rules": template.default_rules,
        "pages": pages,
    }


def build_effective_display_config(*, plan: str, custom_config: dict[str, Any]) -> dict[str, Any]:
    normalized_plan = _normalize_plan(plan)
    template_config = _active_template_config(normalized_plan)
    if normalized_plan == "simple":
        return _deep_merge(SIMPLE_PLAN_FIXED_CONFIG, template_config)
    merged = _deep_merge(PRO_PLAN_BASE_CONFIG, template_config)
    merged = _deep_merge(merged, custom_config)
    merged["plan"] = "pro"
    merged["ui_version"] = 1
    return merged


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_datetime(raw_value: Any) -> datetime | None:
    if not raw_value or not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def verify_wordpress_signature(*, body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def is_wordpress_timestamp_fresh(*, timestamp: str, max_age_seconds: int) -> bool:
    """Reject malformed, future, and replayed webhook timestamps."""
    try:
        received_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    age_seconds = int(datetime.now(timezone.utc).timestamp()) - received_at
    return 0 <= age_seconds <= max_age_seconds


def _notify_change(*, category: str, title: str, message: str, payload: dict[str, Any]) -> None:
    notification = SyncNotification.objects.create(
        category=category,
        title=title,
        message=message,
        payload=payload,
        delivery_target=settings.SYNC_NOTIFY_WEBHOOK_URL,
    )

    target_url = settings.SYNC_NOTIFY_WEBHOOK_URL
    if not target_url:
        return

    body = json.dumps(
        {
            "category": category,
            "title": title,
            "message": message,
            "payload": payload,
            "timestamp": django_timezone.now().isoformat(),
        }
    ).encode("utf-8")
    req = request.Request(
        target_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5):
            notification.delivered = True
            notification.delivered_at = django_timezone.now()
            notification.save(update_fields=["delivered", "delivered_at"])
    except (error.URLError, TimeoutError):
        return


def _upsert_device(payload: dict[str, Any]) -> tuple[WordPressDevice, str, bool]:
    external_id = str(payload.get("external_id") or payload.get("id") or "").strip()
    if not external_id:
        raise ValueError("Device payload does not include external_id/id")

    normalized_plan = _normalize_plan(payload.get("plan"))
    custom_config = _extract_custom_config(payload)
    defaults = {
        "customer_external_id": str(payload.get("customer_external_id") or payload.get("customer_id") or "").strip(),
        "serial_number": str(payload.get("serial_number") or "").strip(),
        "hardware_model": str(payload.get("hardware_model") or "").strip(),
        "name": str(payload.get("name") or "").strip(),
        "plan": normalized_plan,
        "is_active": bool(payload.get("is_active", True)),
        "metadata": payload.get("metadata") or {},
        "custom_config": custom_config,
        "effective_config": build_effective_display_config(plan=normalized_plan, custom_config=custom_config),
        "last_wordpress_updated_at": _parse_datetime(payload.get("updated_at") or payload.get("last_updated_at")),
    }

    instance, created = WordPressDevice.objects.get_or_create(external_id=external_id, defaults=defaults)
    if created:
        return instance, "created", True

    changed = False
    plan_changed = False
    config_changed = False
    for field, new_value in defaults.items():
        old_value = getattr(instance, field)
        if old_value != new_value:
            setattr(instance, field, new_value)
            changed = True
            if field == "plan":
                plan_changed = True
            if field in {"plan", "custom_config", "effective_config"}:
                config_changed = True

    if changed:
        if config_changed:
            instance.ui_version += 1
        instance.save()
        return instance, "updated", plan_changed
    return instance, "unchanged", False


def _upsert_data_source(payload: dict[str, Any]) -> tuple[WordPressDataSource, str]:
    external_id = str(payload.get("external_id") or payload.get("id") or "").strip()
    if not external_id:
        raise ValueError("Data source payload does not include external_id/id")

    defaults = {
        "key": str(payload.get("key") or "").strip(),
        "label": str(payload.get("label") or payload.get("name") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "config": payload.get("config") or payload.get("metadata") or {},
        "last_wordpress_updated_at": _parse_datetime(payload.get("updated_at") or payload.get("last_updated_at")),
    }

    instance, created = WordPressDataSource.objects.get_or_create(external_id=external_id, defaults=defaults)
    if created:
        return instance, "created"

    changed = False
    for field, new_value in defaults.items():
        if getattr(instance, field) != new_value:
            setattr(instance, field, new_value)
            changed = True

    if changed:
        instance.save()
        return instance, "updated"
    return instance, "unchanged"


def process_wordpress_payload(*, payload: dict[str, Any], source: str) -> dict[str, Any]:
    event_type = str(payload.get("event") or "wordpress.change")
    entity_type = str(payload.get("entity_type") or "")
    entity_payload = payload.get("entity")

    if not isinstance(entity_payload, dict):
        if isinstance(payload.get("device"), dict):
            entity_type = SyncEntityType.DEVICE
            entity_payload = payload["device"]
        elif isinstance(payload.get("data_source"), dict):
            entity_type = SyncEntityType.DATA_SOURCE
            entity_payload = payload["data_source"]
        else:
            entity_payload = payload

    action = "ignored"
    entity_external_id = ""
    status = SyncEventStatus.IGNORED
    message = "Payload ignored"

    try:
        if entity_type == SyncEntityType.DEVICE:
            device, action, plan_changed = _upsert_device(entity_payload)
            entity_external_id = device.external_id
            status = SyncEventStatus.PROCESSED
            message = f"Device {action}"
            if plan_changed:
                message = f"Device {action}, plan changed to {device.plan}"
        elif entity_type == SyncEntityType.DATA_SOURCE:
            data_source, action = _upsert_data_source(entity_payload)
            entity_external_id = data_source.external_id
            status = SyncEventStatus.PROCESSED
            message = f"Data source {action}"
        else:
            entity_type = SyncEntityType.UNKNOWN
    except ValueError as exc:
        status = SyncEventStatus.ERROR
        message = str(exc)

    WordPressSyncEvent.objects.create(
        event_type=event_type,
        entity_type=entity_type,
        entity_external_id=entity_external_id,
        source=source,
        payload=payload,
        payload_hash=_json_hash(payload),
        status=status,
        message=message,
        processed_at=django_timezone.now(),
    )

    if status == SyncEventStatus.PROCESSED and action in {"created", "updated"}:
        _notify_change(
            category="wordpress_sync",
            title=f"{entity_type} {action}",
            message=f"WordPress {entity_type} {entity_external_id} was {action}",
            payload={
                "event": event_type,
                "entity_type": entity_type,
                "entity_external_id": entity_external_id,
                "source": source,
            },
        )
        if entity_type == SyncEntityType.DEVICE and device.is_active and device.provisioning_state == "provisioned":
            from core.tasks import publish_device_config_changed

            publish_device_config_changed.delay(device.external_id, device.ui_version)

    return {
        "event": event_type,
        "entity_type": entity_type,
        "entity_external_id": entity_external_id,
        "action": action,
        "status": status,
        "message": message,
    }


def _fetch_json(url: str) -> Any:
    headers = {"Accept": "application/json"}
    if settings.WORDPRESS_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.WORDPRESS_API_TOKEN}"

    req = request.Request(url, headers=headers, method="GET")
    with request.urlopen(req, timeout=15) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


def _absolute_url(base: str, path_or_url: str) -> str:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return parse.urljoin(base.rstrip("/") + "/", path_or_url.lstrip("/"))


def run_wordpress_pull_sync() -> dict[str, Any]:
    base_url = settings.WORDPRESS_API_BASE_URL.strip()
    if not base_url:
        raise ValueError("WORDPRESS_API_BASE_URL is not configured")

    devices_url = _absolute_url(base_url, settings.WORDPRESS_DEVICES_ENDPOINT)
    sources_url = _absolute_url(base_url, settings.WORDPRESS_DATA_SOURCES_ENDPOINT)

    devices_data = _fetch_json(devices_url)
    sources_data = _fetch_json(sources_url)

    devices = devices_data if isinstance(devices_data, list) else devices_data.get("items", [])
    data_sources = sources_data if isinstance(sources_data, list) else sources_data.get("items", [])

    summary = {
        "devices": {"created": 0, "updated": 0, "unchanged": 0, "errors": 0},
        "data_sources": {"created": 0, "updated": 0, "unchanged": 0, "errors": 0},
    }

    for item in devices:
        try:
            payload = {
                "event": "wordpress.pull.device",
                "entity_type": SyncEntityType.DEVICE,
                "entity": item,
            }
            result = process_wordpress_payload(payload=payload, source=SyncSource.PULL)
            summary["devices"][result["action"]] += 1
        except Exception:
            summary["devices"]["errors"] += 1

    for item in data_sources:
        try:
            payload = {
                "event": "wordpress.pull.data_source",
                "entity_type": SyncEntityType.DATA_SOURCE,
                "entity": item,
            }
            result = process_wordpress_payload(payload=payload, source=SyncSource.PULL)
            summary["data_sources"][result["action"]] += 1
        except Exception:
            summary["data_sources"]["errors"] += 1

    _notify_change(
        category="wordpress_sync",
        title="wordpress pull sync finished",
        message="Pull sync from WordPress completed",
        payload=summary,
    )
    return summary


def get_device_display_config(external_id: str) -> dict[str, Any] | None:
    try:
        device = WordPressDevice.objects.get(external_id=external_id)
    except WordPressDevice.DoesNotExist:
        return None

    return {
        "external_id": device.external_id,
        "name": device.name,
        "plan": device.normalized_plan,
        "is_active": device.is_active,
        "customizable": device.normalized_plan == "pro",
        "ui_version": device.ui_version,
        "effective_config": device.effective_config,
        "last_synced_at": device.last_synced_at,
    }
