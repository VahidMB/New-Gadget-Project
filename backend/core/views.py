import json

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from core.models import ServiceHealth, SyncNotification
from core.services import get_device_display_config, process_wordpress_payload, run_wordpress_pull_sync, verify_wordpress_signature


@api_view(["GET"])
def health(request):
    """
    Service health check endpoint.
    
    Returns overall system health including service statuses.
    Queries ServiceHealth table for real monitoring data.
    """
    try:
        # Fetch latest health checks for all services
        services = ServiceHealth.objects.all()
        service_statuses = {}
        any_down = False
        
        for service in services:
            service_statuses[service.get_service_name_display()] = {
                "status": service.status,
                "response_time_ms": service.response_time_ms,
                "last_check": service.last_check_at.isoformat() if service.last_check_at else None,
                "failed_count": service.failed_count,
            }
            if service.status in ["down", "degraded"]:
                any_down = True
        
        overall_status = "degraded" if any_down else "ok"
        return Response({
            "status": overall_status,
            "service": "gadget-api",
            "services": service_statuses
        })
    except Exception as e:
        return Response({
            "status": "error",
            "service": "gadget-api",
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def wordpress_webhook(request):
    secret = settings.WORDPRESS_WEBHOOK_SECRET
    if not secret:
        return Response({"detail": "WORDPRESS_WEBHOOK_SECRET is not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    signature = request.headers.get("X-WP-Signature", "")
    timestamp = request.headers.get("X-WP-Timestamp", "")
    if not signature or not timestamp:
        return Response({"detail": "Missing signature headers"}, status=status.HTTP_400_BAD_REQUEST)

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
    token = settings.WORDPRESS_SYNC_TRIGGER_TOKEN
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
    limit = min(int(request.query_params.get("limit", 50)), 200)
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


@api_view(["GET"])
def device_display_config(request, external_id: str):
    config = get_device_display_config(external_id)
    if config is None:
        return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(config)


@api_view(["POST"])
def device_heartbeat(request, external_id: str):
    """
    Device heartbeat endpoint.
    
    Called by devices to report their operational status.
    Updates DeviceStatus with latest heartbeat, firmware, battery, and signal info.
    
    Expected JSON payload:
    {
        "status": "online",  # online | offline | updating | error
        "firmware_version": "1.0.2",
        "battery_level": 85,  # 0-100
        "signal_strength": -45,  # dBm, negative
        "error_message": ""  # optional error details
    }
    """
    from django.utils import timezone
    from core.models import WordPressDevice, DeviceStatus
    
    try:
        device = WordPressDevice.objects.get(external_id=external_id)
    except WordPressDevice.DoesNotExist:
        return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return Response({"detail": "Invalid JSON payload"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Extract fields; use defaults if missing
    new_status = payload.get("status", "offline")
    if new_status not in ["online", "offline", "updating", "error"]:
        new_status = "offline"
    
    firmware = payload.get("firmware_version", "")
    battery = max(0, min(100, payload.get("battery_level", 0)))  # Clamp 0-100
    signal = payload.get("signal_strength", 0)
    error_msg = payload.get("error_message", "")
    
    # Update or create DeviceStatus
    device_status, created = DeviceStatus.objects.update_or_create(
        device=device,
        defaults={
            "status": new_status,
            "last_heartbeat_at": timezone.now(),
            "firmware_version": firmware,
            "battery_level": battery,
            "signal_strength": signal,
            "error_message": error_msg,
        }
    )
    
    return Response({
        "acknowledged": True,
        "device_id": external_id,
        "status": device_status.status,
        "last_heartbeat": device_status.last_heartbeat_at.isoformat() if device_status.last_heartbeat_at else None,
    })
