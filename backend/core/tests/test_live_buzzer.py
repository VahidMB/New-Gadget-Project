from datetime import timedelta, time
from decimal import Decimal
from unittest.mock import patch
import hashlib
import hmac
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import (BuzzerRule, BuzzerEvent, WordPressDevice, SourceSelection, PriceList, PriceItem, MessageCampaign, AuditEvent, Integration)
from core.tests.test_price_platform import account, source
from core.source_engine import store_value, read_value
from core.buzzer import evaluate_device, number
from core.runtime import platform_settings
from core.platform_tasks import expire_content
from core.secrets import encrypt


@pytest.fixture
def device_source():
    company, user, membership, device = account()
    obj = source()
    SourceSelection.objects.create(device=device, source=obj)
    WordPressDevice.objects.filter(pk=device.pk).update(provisioning_state="provisioned")
    device.refresh_from_db()
    return device, obj, user


@pytest.fixture(autouse=True)
def no_broker():
    with patch("core.buzzer.notify_source"):
        yield


def observe(device, obj, value):
    obj.refresh_from_db()
    assert store_value(obj, {"value": str(value)})
    return evaluate_device(device)


@pytest.mark.parametrize("trigger,threshold,old,new,expected", [
    ("new", None, "news A", "news B", 1),
    ("new", None, "same", "same", 0),
    ("percent", 5, 100, 106, 1),
    ("percent", 5, 100, 104, 0),
    ("percent", 5, 0, 100, 0),
    ("absolute", 20, 100, 79, 1),
    ("above", 120, 100, 120, 1),
    ("above", 120, 121, 130, 0),
    ("below", 80, 100, 79, 1),
])
def test_buzzer_trigger_semantics(device_source, trigger, threshold, old, new, expected):
    device, obj, _ = device_source
    BuzzerRule.objects.create(device=device, name="Alert", trigger=trigger, threshold=threshold)
    assert observe(device, obj, old) == 0
    assert observe(device, obj, new) == expected
    assert BuzzerEvent.objects.filter(device=device).count() == expected


def test_direction_cooldown_quiet_and_first_sample(device_source):
    device, obj, _ = device_source
    rule = BuzzerRule.objects.create(device=device, name="Up", trigger="percent", threshold=5, direction="up", cooldown_seconds=60)
    assert observe(device, obj, 100) == 0
    assert observe(device, obj, 80) == 0
    assert observe(device, obj, 100) == 1
    assert observe(device, obj, 110) == 0
    rule.enabled = False
    rule.save()
    assert device.buzzer_events.filter(expires_at__gt=timezone.now()).count() == 0
    quiet_rule = BuzzerRule.objects.create(device=device, name="Quiet", notify_first=True, quiet_start=time(0), quiet_end=time(23,59,59))
    assert observe(device, obj, 120) == 0
    assert quiet_rule.last_triggered_at is None


def test_personal_and_company_user_can_save_buzzer_rule_but_not_foreign(device_source):
    device, _, user = device_source
    _, _, _, foreign = account("foreign")
    client = Client()
    client.force_login(user)
    fields = {"name": "New information", "enabled": "on", "scope": "all", "trigger": "new", "direction": "both", "window_seconds": 0, "duration_ms": 300, "repeat": 2, "gap_ms": 100, "cooldown_seconds": 60, "max_per_hour": 10, "weekdays": [0, 1]}
    assert client.post(f"/panel/devices/{device.pk}/buzzer/new/", fields).status_code == 302
    assert device.buzzer_rules.get().weekdays == [0, 1]
    assert client.post(f"/panel/devices/{foreign.pk}/buzzer/new/", fields).status_code == 404
    assert not foreign.buzzer_rules.exists()
    device.refresh_from_db()
    assert device.effective_config["buzzer"]["rules"][0]["duration_ms"] == 300


def test_source_push_signature_replay_expiry_and_mapping():
    obj = source(update_mode="push", value_path="data.price", encrypted_push_secret=encrypt("x"*32))
    stamp = str(int(timezone.now().timestamp()))
    raw = json.dumps({"data": {"price": 1234}}).encode()
    event = "event-1"
    signed = hmac.new(b"x"*32, (stamp+"."+event+".").encode()+raw, hashlib.sha256).hexdigest()
    auth = {"HTTP_X_SOURCE_TIMESTAMP": stamp, "HTTP_X_SOURCE_EVENT": event, "HTTP_X_SOURCE_SIGNATURE": signed}
    client = APIClient()
    url = f"/api/v1/sources/{obj.pk}/push/"
    assert client.post(url, raw, content_type="application/json", **auth).json()["accepted"]
    assert read_value(obj)["value"] == "1234"
    assert client.post(url, raw, content_type="application/json", **auth).json()["duplicate"]
    auth["HTTP_X_SOURCE_SIGNATURE"] = "invalid"
    assert client.post(url, raw, content_type="application/json", **auth).status_code == 401
    auth["HTTP_X_SOURCE_TIMESTAMP"] = str(int(timezone.now().timestamp())-1000)
    assert client.post(url, raw, content_type="application/json", **auth).status_code == 400


def test_cleanup_preserves_critical_data_and_logs_and_can_be_disabled():
    company, user, _, device = account()
    prices = PriceList.objects.create(company=company, name="Prices")
    expired = timezone.now()-timedelta(days=100)
    keep = PriceItem.objects.create(price_list=prices, name="Important", code="keep", amount=1, valid_until=expired)
    temporary = PriceItem.objects.create(price_list=prices, name="Temporary", code="temp", amount=2, valid_until=expired, disposable=True)
    message = MessageCampaign.objects.create(company=company, name="Notice", message="Permanent record", expires_at=expired)
    event = AuditEvent.objects.create(actor=user, action="important", object_label="record")
    AuditEvent.objects.filter(pk=event.pk).update(created_at=expired)
    config = platform_settings()
    config.cleanup_enabled = False
    config.save()
    assert expire_content() == 0
    temporary.refresh_from_db()
    assert temporary.amount == 2
    config.cleanup_enabled = True
    config.save()
    assert expire_content() == 1
    keep.refresh_from_db()
    message.refresh_from_db()
    assert keep.amount == 1 and message.message == "Permanent record"
    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_tls_permissions_exact_configured_domain_only():
    config = platform_settings()
    config.setup_complete = config.managed_tls = True
    config.public_base_url = "https://panel.example.com"
    config.save()
    client = Client()
    assert client.get("/api/v1/internal/tls-permission/?domain=panel.example.com").status_code == 204
    assert client.get("/api/v1/internal/tls-permission/?domain=evil.example.com").status_code == 403


def test_graphical_connections_and_integration_fields():
    user = get_user_model().objects.create_superuser(username="owner", password="test-password")
    client = Client()
    client.force_login(user)
    assert client.get("/panel/connections/").status_code == 200
    response = client.get("/panel/integrations/new/")
    assert b'name="options"' not in response.content
    for name in ["devices_endpoint", "sources_endpoint", "topic_root", "auth_header"]:
        assert f'name="{name}"'.encode() in response.content


def test_mqtt_bootstrap_secret_requires_device_auth_and_ack_is_scoped(device_source):
    from core.device_auth import generate_device_token
    device, obj, _ = device_source
    token, digest = generate_device_token()
    WordPressDevice.objects.filter(pk=device.pk).update(device_token_hash=digest)
    client = APIClient()
    url = f"/api/v1/devices/{device.external_id}/connections/"
    assert client.get(url).status_code == 401
    response = client.get(url, HTTP_X_DEVICE_TOKEN=token)
    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    password = response.json()["mqtt"]["password"]
    device.refresh_from_db()
    assert password not in str(device.effective_config)
    BuzzerRule.objects.create(device=device, name="First", notify_first=True)
    assert observe(device, obj, 100) == 1
    event = device.buzzer_events.get()
    ack = f"/api/v1/devices/{device.external_id}/buzzer/{event.pk}/ack/"
    assert client.post(ack, HTTP_X_DEVICE_TOKEN=token).json()["acknowledged"]
    from core.buzzer import pending_events
    assert pending_events(device) == []
    assert BuzzerEvent.objects.filter(pk=event.pk).exists()


def test_broker_renderer_generates_scoped_acl_and_no_plain_password(tmp_path):
    from core.management.commands.render_broker_credentials import render
    _, _, _, device = account()
    WordPressDevice.objects.filter(pk=device.pk).update(provisioning_state="provisioned")
    integration = Integration.objects.create(key="mqtt", name="MQTT", kind="mqtt", username="gadget-backend")
    integration.set_secret("publisher-secret")
    integration.save()
    def fake_hash(command, **kwargs):
        from pathlib import Path
        file = Path(command[-1])
        file.write_text("\n".join(row.split(":")[0]+":$hash" for row in file.read_text().splitlines()))
    with patch("core.management.commands.render_broker_credentials.subprocess.run", side_effect=fake_hash) as hashing:
        assert render(tmp_path) == 2
        assert hashing.call_args.args[0][1] == "-U"
        assert "publisher-secret" not in (tmp_path/"passwords").read_text()
        acl = (tmp_path/"acl").read_text()
        assert f"user device-{device.pk}" in acl
        assert f"topic read gadget/v1/devices/{device.external_id}/events/#" in acl
        assert "topic read #" not in acl
        integration.is_active = False
        integration.set_secret("")
        integration.save()
        assert render(tmp_path) == 0
        assert (tmp_path/"passwords").read_text() == ""


def test_persian_numeric_prices():
    assert number("۱۲٬۳۴۵٫۵") == Decimal("12345.5")
    assert number("NaN") is None
    assert number("یک خبر") is None


def test_new_company_message_buzzes_after_initial_baseline(device_source):
    device, _, _ = device_source
    BuzzerRule.objects.create(device=device, name="Company messages", scope="messages")
    assert evaluate_device(device) == 0
    campaign = MessageCampaign.objects.create(company=device.company, name="New", message="New message", status="sent", expires_at=timezone.now()+timedelta(minutes=1))
    campaign.target_devices.add(device)
    assert evaluate_device(device) == 1
    assert evaluate_device(device) == 0


def test_boundary_window_and_hourly_cap(device_source):
    device, obj, _ = device_source
    rule = BuzzerRule.objects.create(device=device, name="Window", trigger="percent", threshold=5, window_seconds=300, max_per_hour=1)
    assert observe(device, obj, 100) == 0
    assert observe(device, obj, 103) == 0
    assert observe(device, obj, 106) == 1
    BuzzerRule.objects.filter(pk=rule.pk).update(last_triggered_at=timezone.now()-timedelta(minutes=2))
    assert observe(device, obj, 112) == 0


def test_stream_is_scoped_and_first_event_is_delivered(device_source):
    device, _, user = device_source
    _, _, _, foreign = account("foreign")
    client = Client()
    client.force_login(user)
    assert client.get(f"/panel/live/stream/?device={foreign.pk}").status_code == 404
    response = client.get(f"/panel/live/stream/?device={device.pk}")
    iterator = iter(response.streaming_content)
    assert b"retry:" in next(iterator)
    assert b"revision" in next(iterator)
    response.close()


def test_source_graphical_push_form_needs_no_polling_endpoint():
    from core.platform_forms import SourceForm
    form = SourceForm({"name": "Live price", "source_type": "http", "category": "price", "display_key": "live", "update_mode": "push", "value_path": "price", "ttl_seconds": 60, "refresh_interval_seconds": 60, "push_secret": "x"*32, "is_active": True})
    assert form.is_valid(), form.errors
    obj = form.save()
    assert obj.encrypted_push_secret and "x"*32 not in obj.encrypted_push_secret


def test_critical_expired_price_not_shown_in_detail_without_javascript():
    company, user, _, _ = account()
    prices = PriceList.objects.create(company=company, name="Expired")
    PriceItem.objects.create(price_list=prices, code="A", name="A", amount=987654321, valid_until=timezone.now()-timedelta(days=1))
    client = Client()
    client.force_login(user)
    response = client.get(f"/panel/prices/{prices.pk}/")
    assert "۹۸۷٬۶۵۴٬۳۲۱" not in response.content.decode()
    assert prices.items.get().amount == 987654321


def test_query_api_key_is_injected_only_for_bound_origin_and_not_persisted():
    from core.source_engine import refresh_source
    credential = Integration.objects.create(key="query-provider", name="Query provider", kind="provider", endpoint="https://provider.example", options={"auth_location": "query", "auth_parameter": "apikey"})
    credential.set_secret("private-query-token")
    credential.save()
    obj = source(endpoint_url="https://provider.example/prices?symbol=BTC", credential_reference=credential.key, value_path="price")
    with patch("core.source_engine.fetch_public", return_value='{"price":100}') as fetch:
        assert refresh_source(obj)
        url = fetch.call_args.args[0]
        assert "apikey=private-query-token" in url and "symbol=BTC" in url
    obj.refresh_from_db()
    assert "private-query-token" not in obj.endpoint_url
    assert not AuditEvent.objects.filter(object_label__contains="private-query-token").exists()


def test_managed_connection_form_validates_domain_and_refreshes_device_contract():
    from core.platform_forms import ConnectionSettingsForm
    from core.connections import device_connection_config
    _, _, _, device = account()
    config = platform_settings()
    data = {"public_base_url": "https://panel.example.com", "managed_tls": True, "device_mqtt_host": "panel.example.com", "device_mqtt_port": 443, "device_mqtt_transport": "websockets", "device_mqtt_tls": True, "device_mqtt_path": "/mqtt", "device_heartbeat_seconds": 45, "wordpress_poll_seconds": 60, "wordpress_signature_max_age": 120}
    form = ConnectionSettingsForm(data, instance=config)
    assert form.is_valid(), form.errors
    form.save()
    device.refresh_from_db()
    assert device.effective_config["connections"]["heartbeat_seconds"] == 45
    assert device_connection_config(device)["mqtt"]["host"] == "panel.example.com"
    data["public_base_url"] = "https://owner:secret@panel.example.com"
    assert not ConnectionSettingsForm(data, instance=config).is_valid()
