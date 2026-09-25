import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.access import is_platform_user
from core.firmware import select_firmware_release
from core.device_auth import check_device_token
from core.metrics import render_metrics
from core.runtime import runtime_setting, platform_settings
from core.models import DeviceStatus, FirmwareDeployment, FirmwareRelease, ServiceHealth, SyncNotification, WordPressDevice
from core.services import (
    get_device_display_config,
    is_wordpress_timestamp_fresh,
    process_wordpress_payload,
    run_wordpress_pull_sync,
    verify_wordpress_signature,
)


@api_view(["GET"])
def health(request):
    """Return the most recently recorded state of monitored services."""
    stale_after = timezone.now() - timedelta(seconds=settings.HEALTH_CHECK_STALE_AFTER_SECONDS)
    statuses = {}
    overall_status = "ok"

    for service in ServiceHealth.objects.all():
        is_stale = service.last_check_at < stale_after
        service_status = "down" if is_stale else service.status
        statuses[service.service_name] = {
            "label": service.get_service_name_display(),
            "status": service_status,
            "response_time_ms": service.response_time_ms,
            "last_check_at": service.last_check_at.isoformat(),
            "stale": is_stale,
        }
        if service_status == "down":
            overall_status = "down"
        elif service_status == "degraded" and overall_status == "ok":
            overall_status = "degraded"

    if not statuses:
        overall_status = "unknown"

    http_status = status.HTTP_503_SERVICE_UNAVAILABLE if overall_status == "down" else status.HTTP_200_OK
    return Response({"status": overall_status, "service": "gadget-api", "services": statuses}, status=http_status)


def metrics(request):
    """Expose Prometheus metrics; require a bearer token when configured."""
    configured_token = runtime_setting("METRICS_TOKEN")
    if configured_token and not secrets.compare_digest(
        request.headers.get("Authorization", "").removeprefix("Bearer "), configured_token
    ):
        return HttpResponse("Unauthorized\n", status=401)
    return HttpResponse(render_metrics(), content_type="text/plain; version=0.0.4; charset=utf-8")


@api_view(["POST"])
def wordpress_webhook(request):
    secret = runtime_setting("WORDPRESS_WEBHOOK_SECRET")
    if not secret:
        return Response({"detail": "WORDPRESS_WEBHOOK_SECRET is not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    signature = request.headers.get("X-WP-Signature", "")
    timestamp = request.headers.get("X-WP-Timestamp", "")
    if not signature or not timestamp:
        return Response({"detail": "Missing signature headers"}, status=status.HTTP_400_BAD_REQUEST)
    if not is_wordpress_timestamp_fresh(
        timestamp=timestamp,
        max_age_seconds=platform_settings().wordpress_signature_max_age,
    ):
        return Response({"detail": "Expired or invalid webhook timestamp"}, status=status.HTTP_401_UNAUTHORIZED)

    body = request.body
    if not verify_wordpress_signature(body=body, timestamp=timestamp, signature=signature, secret=secret):
        return Response({"detail": "Invalid webhook signature"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    result = process_wordpress_payload(payload=payload, source="webhook")
    return Response(result, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
def wordpress_pull_sync(request):
    token = runtime_setting("WORDPRESS_SYNC_TRIGGER_TOKEN")
    if not token:
        return Response(
            {"detail": "WORDPRESS_SYNC_TRIGGER_TOKEN is not configured"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provided = request.headers.get("X-Sync-Token", "")
    if provided != token:
        return Response({"detail": "Invalid sync trigger token"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        summary = run_wordpress_pull_sync()
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"status": "ok", "summary": summary}, status=status.HTTP_200_OK)


@api_view(["GET"])
def wordpress_notifications(request):
    if not is_platform_user(request.user):
        return Response({"detail": "Platform access required"}, status=status.HTTP_403_FORBIDDEN)
    try:
        limit = int(request.query_params.get("limit", 50))
    except (TypeError, ValueError):
        return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
    if not 1 <= limit <= 200:
        return Response({"detail": "limit must be between 1 and 200"}, status=status.HTTP_400_BAD_REQUEST)
    notifications = SyncNotification.objects.all()[:limit]
    data = [
        {
            "id": item.id,
            "category": item.category,
            "title": item.title,
            "message": item.message,
            "payload": item.payload,
            "delivered": item.delivered,
            "delivery_target": item.delivery_target,
            "created_at": item.created_at,
            "delivered_at": item.delivered_at,
        }
        for item in notifications
    ]
    return Response({"count": len(data), "items": data})


def _authenticated_device(request, external_id: str) -> tuple[WordPressDevice | None, Response | None]:
    try:
        device = WordPressDevice.objects.get(external_id=external_id)
    except WordPressDevice.DoesNotExist:
        return None, Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)

    if not device.is_active or not device.customer_enabled or (device.company_id and not device.company.is_active) or (device.assigned_user_id and not device.assigned_user.is_active) or device.provisioning_state != WordPressDevice.ProvisioningState.PROVISIONED:
        return None, Response({"detail": "Device is not authorized"}, status=status.HTTP_403_FORBIDDEN)

    token = request.headers.get("X-Device-Token", "")
    if not check_device_token(token, device.device_token_hash):
        return None, Response({"detail": "Invalid device token"}, status=status.HTTP_401_UNAUTHORIZED)
    return device, None


@api_view(["GET"])
def device_display_config(request, external_id: str):
    _, error_response = _authenticated_device(request, external_id)
    if error_response:
        return error_response
    config = get_device_display_config(external_id)
    if config is None:
        return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(config)


@api_view(["POST"])
def device_heartbeat(request, external_id: str):
    """Record a device's latest operational state."""
    device, error_response = _authenticated_device(request, external_id)
    if error_response:
        return error_response

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(payload, dict):
        return Response({"detail": "JSON payload must be an object"}, status=status.HTTP_400_BAD_REQUEST)

    device_status_value = payload.get("status", "online")
    allowed_statuses = {choice[0] for choice in DeviceStatus.STATUS_CHOICES}
    if device_status_value not in allowed_statuses:
        return Response({"detail": "Invalid device status"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        signal_strength = int(payload.get("signal_strength", 0))
        config_version = int(payload.get("config_version", 0))
    except (TypeError, ValueError):
        return Response({"detail": "Signal and config version must be integers"}, status=status.HTTP_400_BAD_REQUEST)

    if config_version < 0:
        return Response({"detail": "Config version must be non-negative"}, status=status.HTTP_400_BAD_REQUEST)

    device_status, _ = DeviceStatus.objects.update_or_create(
        device=device,
        defaults={
            "status": device_status_value,
            "last_heartbeat_at": timezone.now(),
            "last_config_version": config_version,
            "firmware_version": str(payload.get("firmware_version", ""))[:64],
            "signal_strength": signal_strength,
            "error_message": str(payload.get("error_message", "")),
        },
    )

    return Response({
        "acknowledged": True,
        "device_id": external_id,
        "status": device_status.status,
        "last_heartbeat_at": device_status.last_heartbeat_at.isoformat(),
    })


@api_view(["GET"])
def device_firmware_update_check(request, external_id: str):
    device, error_response = _authenticated_device(request, external_id)
    if error_response:
        return error_response
    if not device.hardware_model:
        return Response({"update_available": False, "detail": "Device hardware model is not configured"})

    current_version = request.query_params.get("firmware_version", "")[:64]
    if not current_version:
        current_version = DeviceStatus.objects.filter(device=device).values_list("firmware_version", flat=True).first() or ""
    release = select_firmware_release(device.hardware_model, current_version)
    if release is None:
        return Response({"update_available": False, "firmware_version": current_version})

    deployment, _ = FirmwareDeployment.objects.get_or_create(device=device, release=release)
    download_url = release.download_url
    if release.firmware_file:
        from django.urls import reverse
        from core.runtime import platform_settings
        path = reverse("firmware-download", args=[external_id, release.pk])
        base = platform_settings().public_base_url
        download_url = base.rstrip("/") + path if base else request.build_absolute_uri(path)
    return Response(
        {
            "update_available": True,
            "deployment_id": deployment.id,
            "version": release.version,
            "download_url": download_url,
            "checksum_sha256": release.checksum_sha256,
            "mandatory": release.is_mandatory,
            "release_notes": release.release_notes,
        }
    )


@api_view(["POST"])
def device_firmware_update_report(request, external_id: str):
    device, error_response = _authenticated_device(request, external_id)
    if error_response:
        return error_response
    if not isinstance(request.data, dict):
        return Response({"detail": "JSON payload must be an object"}, status=status.HTTP_400_BAD_REQUEST)

    release_version = str(request.data.get("release_version", ""))[:64]
    report_status = str(request.data.get("status", ""))
    allowed_statuses = {choice[0] for choice in FirmwareDeployment.Status.choices}
    if not release_version or report_status not in allowed_statuses:
        return Response({"detail": "A valid release_version and status are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        release = FirmwareRelease.objects.get(hardware_model=device.hardware_model, version=release_version)
    except FirmwareRelease.DoesNotExist:
        return Response({"detail": "Firmware release not found"}, status=status.HTTP_404_NOT_FOUND)

    deployment, _ = FirmwareDeployment.objects.get_or_create(device=device, release=release)
    deployment.status = report_status
    deployment.reported_version = str(request.data.get("firmware_version", ""))[:64]
    deployment.error_message = str(request.data.get("error_message", ""))
    deployment.last_reported_at = timezone.now()
    deployment.save()

    if report_status == FirmwareDeployment.Status.INSTALLED:
        DeviceStatus.objects.update_or_create(
            device=device,
            defaults={"firmware_version": deployment.reported_version or release.version, "status": "online"},
        )

    return Response({"acknowledged": True, "deployment_id": deployment.id, "status": deployment.status})
