import hashlib
import hmac
import json

from rest_framework.test import APIClient

from core.models import WordPressDevice


def _sign(secret: str, timestamp: str, payload: bytes) -> str:
    signed = f"{timestamp}.".encode("utf-8") + payload
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def test_wordpress_webhook_upserts_device(settings) -> None:
    settings.WORDPRESS_WEBHOOK_SECRET = "test-secret"
    payload = {
        "event": "device.updated",
        "entity_type": "device",
        "entity": {
            "external_id": "dev-100",
            "customer_external_id": "cust-1",
            "name": "Lobby Device",
            "plan": "vip",
            "custom_config": {"screens": [{"type": "weather", "enabled": False}]},
            "is_active": True,
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    timestamp = "1720000000"
    signature = _sign(settings.WORDPRESS_WEBHOOK_SECRET, timestamp, raw)

    client = APIClient()
    response = client.post(
        "/api/v1/integrations/wordpress/webhook/",
        data=raw,
        content_type="application/json",
        HTTP_X_WP_SIGNATURE=signature,
        HTTP_X_WP_TIMESTAMP=timestamp,
    )

    assert response.status_code == 202
    device = WordPressDevice.objects.get(external_id="dev-100")
    assert device.plan == "pro"
    assert device.normalized_plan == "pro"
    assert device.effective_config["customizable"] is True
    assert device.effective_config["ui_version"] == 1
    assert device.effective_config["plan"] == "pro"


def test_simple_plan_uses_fixed_config(settings) -> None:
    settings.WORDPRESS_WEBHOOK_SECRET = "test-secret"
    payload = {
        "event": "device.updated",
        "entity_type": "device",
        "entity": {
            "external_id": "dev-200",
            "name": "Simple Device",
            "plan": "simple",
            "custom_config": {
                "screens": [{"type": "weather", "enabled": False}],
                "customizable": True,
            },
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    timestamp = "1720000001"
    signature = _sign(settings.WORDPRESS_WEBHOOK_SECRET, timestamp, raw)

    client = APIClient()
    response = client.post(
        "/api/v1/integrations/wordpress/webhook/",
        data=raw,
        content_type="application/json",
        HTTP_X_WP_SIGNATURE=signature,
        HTTP_X_WP_TIMESTAMP=timestamp,
    )

    assert response.status_code == 202
    device = WordPressDevice.objects.get(external_id="dev-200")
    assert device.plan == "simple"
    assert device.normalized_plan == "simple"
    assert device.effective_config["customizable"] is False
    assert device.effective_config["ui_version"] == 1
    assert device.effective_config["plan"] == "simple"
    assert any(screen["type"] == "market" for screen in device.effective_config["screens"])


def test_device_display_config_endpoint(settings) -> None:
    WordPressDevice.objects.create(
        external_id="dev-300",
        name="Pro Device",
        plan="pro",
        custom_config={"screens": [{"type": "news", "enabled": True}]},
        effective_config={"customizable": True, "screens": [{"type": "branding", "enabled": True}]},
    )
    client = APIClient()
    response = client.get("/api/v1/devices/dev-300/display-config/")
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "pro"
    assert body["customizable"] is True
    assert body["ui_version"] == 1


def test_wordpress_pull_sync_requires_token(settings) -> None:
    settings.WORDPRESS_SYNC_TRIGGER_TOKEN = "sync-token"
    client = APIClient()
    response = client.post("/api/v1/integrations/wordpress/sync/", data={}, format="json")
    assert response.status_code == 401
