from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from core.device_auth import generate_device_token
from core.models import DeviceStatus, ServiceHealth, WordPressDevice


def _provisioned_device(external_id: str, **kwargs) -> tuple[WordPressDevice, str]:
    token, token_hash = generate_device_token()
    device = WordPressDevice.objects.create(
        external_id=external_id,
        provisioning_state=WordPressDevice.ProvisioningState.PROVISIONED,
        device_token_hash=token_hash,
        **kwargs,
    )
    return device, token


def test_health_endpoint() -> None:
    client = APIClient()
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_health_endpoint_reports_recorded_service_state() -> None:
    ServiceHealth.objects.create(service_name="db", status="up", response_time_ms=12)

    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["services"]["db"]["status"] == "up"


def test_health_endpoint_marks_stale_service_down(settings) -> None:
    settings.HEALTH_CHECK_STALE_AFTER_SECONDS = 60
    service = ServiceHealth.objects.create(service_name="redis", status="up")
    ServiceHealth.objects.filter(pk=service.pk).update(last_check_at=timezone.now() - timedelta(seconds=61))

    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json()["status"] == "down"
    assert response.json()["services"]["redis"]["stale"] is True


def test_device_heartbeat_updates_device_status() -> None:
    _, token = _provisioned_device("esp32-100")
    client = APIClient()

    response = client.post(
        "/api/v1/devices/esp32-100/heartbeat/",
        {
            "status": "online",
            "firmware_version": "1.2.0",
            "battery_level": 85,
            "signal_strength": -55,
            "config_version": 3,
        },
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "online"
    device = WordPressDevice.objects.get(external_id="esp32-100")
    assert not hasattr(device.status, "battery_level")
    assert device.status.last_config_version == 3


def test_device_heartbeat_ignores_legacy_battery_field() -> None:
    _, token = _provisioned_device("esp32-101")

    response = APIClient().post(
        "/api/v1/devices/esp32-101/heartbeat/",
        {"battery_level": 101},
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
    )

    assert response.status_code == 200


def test_device_heartbeat_requires_a_valid_token() -> None:
    _provisioned_device("esp32-102")

    response = APIClient().post("/api/v1/devices/esp32-102/heartbeat/", {"status": "online"}, format="json")

    assert response.status_code == 401


def test_provision_command_prints_a_token_once_and_stores_only_its_hash() -> None:
    device = WordPressDevice.objects.create(external_id="esp32-104")
    output = StringIO()

    call_command("provision_device", device.external_id, stdout=output)

    token = output.getvalue().strip()
    device.refresh_from_db()
    assert token
    assert token not in device.device_token_hash
    assert device.provisioning_state == WordPressDevice.ProvisioningState.PROVISIONED

    rotated_output = StringIO()
    call_command("provision_device", device.external_id, "--rotate", stdout=rotated_output)
    assert rotated_output.getvalue().strip() != token


def test_stale_devices_are_marked_offline(settings) -> None:
    from core.monitoring import mark_stale_devices_offline

    from core.models import PlatformSettings
    PlatformSettings.objects.create(heartbeat_timeout=60)
    device, _ = _provisioned_device("esp32-103")
    DeviceStatus.objects.create(device=device, status="online", last_heartbeat_at=timezone.now() - timedelta(seconds=61))

    assert mark_stale_devices_offline() == 1
    device.status.refresh_from_db()
    assert device.status.status == "offline"
