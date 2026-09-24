import secrets
from datetime import datetime, timezone as dt_timezone
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import Integration, ExternalDataSource
from core.views import _authenticated_device
from core.source_engine import extract, store_value
from core.content import device_content


@api_view(["GET"])
def content(request, external_id):
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    data = device_content(device)
    from core.buzzer import pending_events
    data["buzzer_events"] = pending_events(device)
    response = Response(data)
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
def telegram_webhook(request, key):
    bot = Integration.objects.filter(key=key, kind="telegram", is_active=True).first()
    expected = bot.secret(webhook=True) if bot else ""
    if not expected or not secrets.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), expected):
        return Response({"detail": "Unauthorized"}, status=401)
    body = request.data
    if not isinstance(body, dict) or not isinstance(body.get("update_id"), int):
        return Response({"detail": "Invalid update"}, status=400)
    event = body.get("channel_post") or body.get("edited_channel_post") or body.get("message") or body.get("edited_message")
    if not isinstance(event, dict):
        return Response({"accepted": True, "matched": 0})
    chat = event.get("chat")
    if not isinstance(chat, dict) or "id" not in chat:
        return Response({"detail": "Invalid chat"}, status=400)
    raw = event.get("text") or event.get("caption") or ""
    if not isinstance(raw, str) or len(raw) > 10000:
        return Response({"detail": "Invalid text"}, status=400)
    try:
        observed = datetime.fromtimestamp(int(event.get("edit_date") or event["date"]), tz=dt_timezone.utc)
    except (ValueError, KeyError, TypeError, OverflowError):
        return Response({"detail": "Invalid timestamp"}, status=400)
    if observed > timezone.now():
        return Response({"detail": "Future timestamp"}, status=400)
    replay_key = f"telegram-update:{bot.pk}:{body['update_id']}"
    if not cache.add(replay_key, True, 86400):
        return Response({"accepted": True, "duplicate": True})
    # A company bot cannot feed another company's sources or global public sources.
    sources = ExternalDataSource.objects.filter(source_type="telegram", company_id=bot.company_id, telegram_chat_id=str(chat["id"]), is_active=True).filter(credential_reference=bot.key)
    matched = 0
    for source in sources:
        try:
            if store_value(source, extract(source, raw), observed):
                matched += 1
        except (ValueError, TimeoutError):
            continue
    from core.models import ServiceHealth
    ServiceHealth.objects.update_or_create(service_name="telegram", defaults={"status": "up"})
    return Response({"accepted": True, "matched": matched})


@api_view(["GET"])
def firmware_download(request, external_id, release_id):
    from django.http import FileResponse
    from core.models import FirmwareRelease
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    from django.db.models import Q
    release = FirmwareRelease.objects.filter(pk=release_id, hardware_model=device.hardware_model, is_active=True).filter(Q(published_at__isnull=True) | Q(published_at__lte=timezone.now())).first()
    if not release or not release.firmware_file:
        return Response({"detail": "Firmware file not found"}, status=404)
    return FileResponse(release.firmware_file.open("rb"), as_attachment=True, filename=f"firmware-{release.pk}.bin")


@api_view(["POST"])
def resource_report(request):
    import math
    import re
    from core.models import ResourceSnapshot, ServiceHealth
    integration = Integration.objects.filter(key="monitor", kind="monitor", is_active=True, company__isnull=True).first()
    token = integration.secret() if integration else ""
    if not token or not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + token):
        return Response({"detail": "Unauthorized"}, status=401)
    payload = request.data
    if not isinstance(payload, dict) or not isinstance(payload.get("services"), list) or len(payload["services"]) > 50:
        return Response({"detail": "Expected services list (max 50)"}, status=400)
    parsed = []
    for sample in payload["services"]:
        if not isinstance(sample, dict) or not re.fullmatch(r"[a-z0-9_-]{1,48}", str(sample.get("service", ""))):
            return Response({"detail": "Invalid service name"}, status=400)
        fields = {}
        for key in ["cpu_percent", "memory_bytes", "disk_bytes", "network_rx_bytes", "network_tx_bytes"]:
            value = sample.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 10**16):
                return Response({"detail": "Invalid resource value"}, status=400)
            fields[key] = value
        if sample.get("status", "up") not in {"up", "down", "degraded"}:
            return Response({"detail": "Invalid service status"}, status=400)
        parsed.append((sample, fields))
    for sample, fields in parsed:
        ResourceSnapshot.objects.update_or_create(service=sample["service"], defaults={**fields, "origin": "authenticated collector"})
        ServiceHealth.objects.update_or_create(service_name=sample["service"], defaults={"status": sample.get("status", "up")})
    return Response({"accepted": len(parsed)})


@api_view(["POST"])
def source_push(request, source_id):
    """Authenticated per-source JSON ingress; the observed time must be signed with the body."""
    import hashlib
    import hmac
    import json
    from core.secrets import decrypt
    source = ExternalDataSource.objects.filter(pk=source_id, update_mode="push", source_type="http", is_active=True).first()
    if not source or not source.encrypted_push_secret:
        return Response({"detail": "Unauthorized"}, status=401)
    stamp = request.headers.get("X-Source-Timestamp", "")
    event_id = request.headers.get("X-Source-Event", "")
    raw = request.body
    if len(raw) > 65536 or not event_id or len(event_id) > 100:
        return Response({"detail": "Invalid event"}, status=400)
    try:
        observed = datetime.fromtimestamp(int(stamp), tz=dt_timezone.utc)
    except (ValueError, OverflowError, OSError):
        return Response({"detail": "Invalid timestamp"}, status=400)
    age = (timezone.now()-observed).total_seconds()
    if age < -5 or age > min(source.ttl_seconds, 300):
        return Response({"detail": "Expired timestamp"}, status=400)
    signature = hmac.new(decrypt(source.encrypted_push_secret).encode(), (stamp+"."+event_id+".").encode()+raw, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(signature, request.headers.get("X-Source-Signature", "")):
        return Response({"detail": "Unauthorized"}, status=401)
    try:
        json.loads(raw)
        content = extract(source, raw.decode("utf-8"))
    except (ValueError, TypeError, KeyError, IndexError, UnicodeDecodeError, TimeoutError):
        return Response({"detail": "Payload does not match source mapping"}, status=400)
    replay = "source-event:" + hashlib.sha256(f"{source.pk}:{event_id}".encode()).hexdigest()
    if not cache.add(replay, True, max(source.ttl_seconds, 300)):
        return Response({"accepted": True, "duplicate": True})
    accepted = store_value(source, content, min(observed, timezone.now()))
    return Response({"accepted": accepted})


@api_view(["POST"])
def buzzer_ack(request, external_id, event_id):
    from core.models import BuzzerEvent
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    count = BuzzerEvent.objects.filter(pk=event_id, device=device).update(acknowledged_at=timezone.now())
    return Response({"acknowledged": bool(count)}, status=200 if count else 404)


@api_view(["GET"])
def device_connections(request, external_id):
    from core.connections import device_connection_config, broker_credential
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    data = device_connection_config(device)
    data["mqtt"]["password"] = broker_credential(device)
    response = Response(data)
    response["Cache-Control"] = "no-store"
    return response


def tls_permission(request):
    from django.http import HttpResponse
    from urllib.parse import urlsplit
    from core.runtime import platform_settings
    config = platform_settings()
    configured = urlsplit(config.public_base_url).hostname
    allowed = config.setup_complete and config.managed_tls and configured and request.GET.get("domain", "").lower() == configured.lower()
    return HttpResponse(status=204 if allowed else 403)
