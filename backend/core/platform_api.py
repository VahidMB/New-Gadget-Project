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
    response = Response(device_content(device))
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
