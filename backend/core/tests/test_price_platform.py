from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from core.access import visible_devices, rule_for
from core.content import device_content, purge_expired_content
from core.models import (Company, CompanyMembership, WordPressDevice, ExternalDataSource, SourceSelection, PriceList, PriceItem, MessageCampaign, Integration, ResourceSnapshot, CampaignDelivery)
from core.source_engine import extract, fetch_public, store_value, read_value, cache_key


def account(name="first", plan="pro", parent=None):
    company = Company.objects.create(name=name, slug=name, parent=parent)
    user = get_user_model().objects.create_user(username=name, password="local-test-password")
    membership = CompanyMembership.objects.create(user=user, company=company, role="company_admin")
    device = WordPressDevice.objects.create(company=company, external_id=name, plan=plan, assigned_user=user)
    return company, user, membership, device


def source(company=None, **kwargs):
    key = kwargs.pop("display_key", "gold")
    return ExternalDataSource.objects.create(company=company, name=key, display_key=key, **kwargs)


def test_revoked_membership_removes_assigned_device_access():
    company, user, membership, device = account()
    assert visible_devices(user).filter(pk=device.pk).exists()
    membership.is_active = False
    membership.save()
    assert not visible_devices(user).exists()
    client = Client()
    client.force_login(user)
    assert client.get(f"/panel/devices/{device.pk}/").status_code == 404


def test_parent_company_sees_descendants_but_not_siblings():
    parent, user, _, _ = account("parent")
    _, child_user, _, child = account("child", parent=parent)
    _, _, _, outsider = account("outsider")
    assert visible_devices(user).filter(pk=child.pk).exists()
    assert not visible_devices(user).filter(pk=outsider.pk).exists()
    assert set(visible_devices(child_user).values_list("pk", flat=True)) == {child.pk}


def test_expired_prices_and_messages_are_masked_then_erased():
    company, _, _, device = account()
    price_list = PriceList.objects.create(company=company, name="Products")
    price_list.target_devices.add(device)
    price = PriceItem.objects.create(price_list=price_list, name="Cable", code="A", amount=Decimal("125000"), valid_until=timezone.now()-timedelta(seconds=1))
    message = MessageCampaign.objects.create(company=company, name="Offer", message="old body", status="sent", expires_at=timezone.now()-timedelta(seconds=1))
    message.target_devices.add(device)
    payload = device_content(device)
    assert payload["price_lists"][0]["items"][0]["amount"] is None
    assert payload["messages"] == []
    assert purge_expired_content() == 2
    price.refresh_from_db()
    message.refresh_from_db()
    assert price.amount is None and message.message == ""


def test_private_sources_cannot_cross_tenants_or_survive_plan_downgrade():
    company, _, _, device = account()
    foreign, _, _, _ = account("foreign")
    own, other, public = source(company), source(foreign), source()
    for value in (own, other, public):
        SourceSelection.objects.create(device=device, source=value)
    assert {s["id"] for s in device_content(device)["sources"]} == {own.pk, public.pk}
    device.plan = "simple"
    device.save()
    assert [s["id"] for s in device_content(device)["sources"]] == [public.pk]


def test_quota_applies_to_both_content_and_effective_config():
    company, _, _, device = account()
    rule = rule_for("pro")
    rule.max_sources = 1
    rule.save()
    for key in ("first", "second"):
        SourceSelection.objects.create(device=device, source=source(company, display_key=key))
    device.refresh_from_db()
    assert len(device_content(device)["sources"]) == 1
    assert device.effective_config["selected_sources"] == ["first"]


@pytest.mark.parametrize("kind,path,raw,expected", [
    ("http", "data.0.price", '{"data":[{"price":42}]}', "42"),
    ("web", ".price", '<div class="price">125<script>bad()</script></div>', "125"),
    ("rss", "description", '<rss><item><title>T</title><description>News</description></item></rss>', "News"),
    ("telegram", "", "Gold: 4200 USD", "4200"),
])
def test_source_extractors(kind, path, raw, expected):
    obj = source(source_type=kind, value_path=path, extraction_pattern=r"Gold: (\d+)" if kind == "telegram" else "")
    assert extract(obj, raw)["value"] == expected


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fd00::1"])
def test_source_fetch_rejects_private_dns_before_connect(address):
    with patch("core.source_engine.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 443))]), patch("core.source_engine.socket.create_connection") as connect:
        with pytest.raises(ValueError):
            fetch_public("https://source.example/price")
        connect.assert_not_called()


def test_expired_cache_data_never_returns_even_if_backend_retains_it():
    obj = source(ttl_seconds=60)
    assert not store_value(obj, {"value": "old"}, timezone.now()-timedelta(seconds=61))
    assert store_value(obj, {"value": "fresh"})
    assert read_value(obj)["value"] == "fresh"
    value = cache.get(cache_key(obj))
    value["expires_at"] = (timezone.now()-timedelta(seconds=1)).isoformat()
    cache.set(cache_key(obj), value)
    assert read_value(obj) is None


def test_telegram_auth_scope_replay_and_original_timestamp():
    company, _, _, _ = account()
    foreign, _, _, _ = account("other")
    bot = Integration.objects.create(key="company-bot", name="Bot", kind="telegram", company=company)
    bot.set_secret("webhook-secret", webhook=True)
    bot.save()
    own = source(company, source_type="telegram", telegram_chat_id="-42", credential_reference=bot.key, ttl_seconds=60)
    other = source(foreign, source_type="telegram", telegram_chat_id="-42", credential_reference=bot.key)
    url = f"/api/v1/integrations/telegram/{bot.key}/webhook/"
    payload = {"update_id": 1, "channel_post": {"chat": {"id": -42}, "date": int(timezone.now().timestamp()), "text": "Gold 100"}}
    client = APIClient()
    assert client.post(url, payload, format="json").status_code == 401
    auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "webhook-secret"}
    assert client.post(url, payload, format="json", **auth).json()["matched"] == 1
    assert read_value(own)["value"] == "Gold 100" and read_value(other) is None
    assert client.post(url, payload, format="json", **auth).json()["duplicate"]
    cache.clear()
    payload["update_id"] = 2
    payload["channel_post"]["date"] -= 120
    assert client.post(url, payload, format="json", **auth).json()["matched"] == 0
    assert read_value(own) is None


def test_monitor_rejects_invalid_batch_without_partial_writes():
    integration = Integration.objects.create(key="monitor", name="Monitor", kind="monitor")
    integration.set_secret("collector-secret")
    integration.save()
    client = APIClient()
    url = "/api/v1/monitoring/resources/"
    data = {"services": [{"service": "api", "cpu_percent": 5, "memory_bytes": 1024}]}
    assert client.post(url, data, format="json").status_code == 401
    auth = {"HTTP_AUTHORIZATION": "Bearer collector-secret"}
    bad = {"services": data["services"] + [{"service": "worker", "memory_bytes": -1}]}
    assert client.post(url, bad, format="json", **auth).status_code == 400
    assert not ResourceSnapshot.objects.exists()
    assert client.post(url, data, format="json", **auth).json()["accepted"] == 1
    assert ResourceSnapshot.objects.get(service="api").memory_bytes == 1024


def test_customer_cannot_unsuspend_admin_disabled_device_or_bulk_foreign_device():
    _, user, _, device = account()
    _, _, _, foreign = account("foreign")
    device.is_active = False
    device.provisioning_state = "suspended"
    device.save()
    client = Client()
    client.force_login(user)
    assert client.post(f"/panel/devices/{device.pk}/activation/").status_code == 403
    assert client.post("/panel/devices/bulk/", {"devices": [device.pk], "operation": "enable"}).status_code == 403
    assert client.post("/panel/devices/bulk/", {"devices": [foreign.pk], "operation": "disable"}).status_code == 403
    foreign.refresh_from_db()
    assert foreign.customer_enabled


def test_campaign_retries_failed_recipient_without_resending_successful_one():
    from core.platform_tasks import dispatch_campaigns
    company, _, _, first = account()
    second = WordPressDevice.objects.create(company=company, external_id="second", plan="pro")
    WordPressDevice.objects.filter(pk__in=[first.pk, second.pk]).update(provisioning_state="provisioned")
    campaign = MessageCampaign.objects.create(company=company, name="Prices", message="New", scheduled_at=timezone.now()-timedelta(seconds=1), expires_at=timezone.now()+timedelta(minutes=5), status="scheduled")
    campaign.target_devices.add(first, second)
    with patch("core.platform_tasks.publish_device_message", side_effect=[None, OSError("broker down")]):
        assert dispatch_campaigns() == 0
    assert CampaignDelivery.objects.filter(delivered_at__isnull=False).count() == 1
    with patch("core.platform_tasks.publish_device_message") as publish:
        assert dispatch_campaigns() == 1
        assert publish.call_count == 1 and publish.call_args.kwargs["retain"] is False
    with patch("core.platform_tasks.publish_device_message") as publish:
        assert dispatch_campaigns() == 0
        publish.assert_not_called()


def test_secrets_encrypted_and_not_rendered_to_admin():
    admin = get_user_model().objects.create_superuser(username="owner", password="strong-test-password")
    integration = Integration.objects.create(key="market-api", name="Prices", kind="provider")
    integration.set_secret("highly-sensitive-token")
    integration.save()
    assert "highly-sensitive-token" not in integration.encrypted_secret
    assert integration.secret() == "highly-sensitive-token"
    client = Client()
    client.force_login(admin)
    response = client.get(f"/panel/integrations/{integration.pk}/")
    assert response.status_code == 200
    assert b"highly-sensitive-token" not in response.content


@pytest.mark.parametrize("path", ["/panel/", "/panel/companies/", "/panel/users/", "/panel/integrations/", "/panel/settings/", "/panel/plans/", "/panel/templates/", "/panel/monitoring/", "/panel/firmware/", "/panel/prices/", "/panel/memberships/"])
def test_admin_pages_render(path):
    admin = get_user_model().objects.create_superuser(username="owner", password="strong-test-password")
    client = Client()
    client.force_login(admin)
    assert client.get(path).status_code == 200


def test_setup_claim_code_is_required_and_setup_can_only_run_once():
    from core.models import PlatformSettings
    client = Client()
    data = {"username": "owner", "password": "Unique$Setup-Password-891!", "public_base_url": "https://panel.example.com", "code": "wrong"}
    with patch("core.secrets.setup_code", return_value="valid-claim-code"):
        assert client.post("/setup/", data).status_code == 200
        assert not get_user_model().objects.filter(is_superuser=True).exists()
        data["code"] = "valid-claim-code"
        assert client.post("/setup/", data).status_code == 302
        assert PlatformSettings.objects.get(pk=1).setup_complete
        assert get_user_model().objects.filter(is_superuser=True).count() == 1
        data["username"] = "second-owner"
        assert client.post("/setup/", data).status_code == 302
        assert not get_user_model().objects.filter(username="second-owner").exists()


def test_provider_credentials_never_follow_a_customer_changed_hostname():
    from core.source_engine import refresh_source
    company, _, _, _ = account()
    credential = Integration.objects.create(company=company, key="provider", name="Trusted", kind="provider", endpoint="https://trusted.example")
    credential.set_secret("secret-token")
    credential.save()
    obj = source(company, endpoint_url="https://attacker.example/collect", credential_reference=credential.key)
    with patch("core.source_engine.fetch_public") as fetch:
        assert not refresh_source(obj)
        fetch.assert_not_called()
    obj.refresh_from_db()
    assert "secret-token" not in obj.last_error


def test_older_telegram_observation_does_not_replace_newer_price():
    obj = source(ttl_seconds=60)
    now = timezone.now()
    assert store_value(obj, {"value": "new"}, now)
    assert not store_value(obj, {"value": "older"}, now-timedelta(seconds=10))
    assert read_value(obj)["value"] == "new"


def test_personal_preferences_save_order_and_ignore_forbidden_fields():
    company, user, _, device = account(plan="simple")
    first = source(display_key="a")
    second = source(display_key="b")
    client = Client()
    client.force_login(user)
    response = client.post(f"/panel/devices/{device.pk}/preferences/", {"theme": "light", "rotation_seconds": 300, "live_updates": "on", "custom_primary": "#ff0000", "sources": [first.pk, second.pk], "ordered_sources": f"{second.pk},{first.pk}"})
    assert response.status_code == 302
    device.refresh_from_db()
    assert device.preferences.theme == "light"
    assert device.preferences.custom_primary == ""
    assert [s["id"] for s in device_content(device)["sources"]] == [second.pk, first.pk]


def test_content_hints_only_publish_when_changed_and_live_is_enabled():
    from core.platform_tasks import publish_content_hints
    from core.models import DevicePreference
    _, _, _, device = account()
    WordPressDevice.objects.filter(pk=device.pk).update(provisioning_state="provisioned")
    with patch("core.platform_tasks.publish_device_message") as publish:
        assert publish_content_hints() == 1
        assert publish.call_args.kwargs["suffix"] == "events/content"
        assert publish_content_hints() == 0
    DevicePreference.objects.create(device=device, live_updates=False)
    with patch("core.platform_tasks.publish_device_message") as publish:
        assert publish_content_hints() == 0
        publish.assert_not_called()


def test_customer_cannot_use_admin_connection_or_plan_pages():
    _, user, _, _ = account()
    client = Client()
    client.force_login(user)
    for path in ["integrations", "settings", "plans", "templates", "monitoring"]:
        assert client.get(f"/panel/{path}/").status_code == 403
    assert client.get("/panel/live/?device=bad-id").status_code == 400


def test_scheduled_price_list_is_not_shared_until_due_delivery():
    from core.platform_tasks import dispatch_campaigns
    company, user, _, device = account()
    prices = PriceList.objects.create(company=company, name="Tomorrow prices")
    client = Client()
    client.force_login(user)
    now = timezone.now()
    response = client.post("/panel/messages/new/", {"company": company.pk, "name": "Tomorrow", "message": "New price list", "price_list": prices.pk, "target_devices": [device.pk], "scheduled_at": (now+timedelta(hours=1)).isoformat(), "expires_at": (now+timedelta(hours=2)).isoformat()})
    assert response.status_code == 302
    assert not prices.target_devices.exists()
    with patch("core.platform_tasks.publish_device_message") as publish:
        assert dispatch_campaigns() == 0
        publish.assert_not_called()
    WordPressDevice.objects.filter(pk=device.pk).update(provisioning_state="provisioned")
    MessageCampaign.objects.update(scheduled_at=now-timedelta(seconds=1))
    with patch("core.platform_tasks.publish_device_message"):
        assert dispatch_campaigns() == 1
    assert prices.target_devices.filter(pk=device.pk).exists()


def test_wordpress_ownership_mapping_requires_active_membership():
    from core.services import process_wordpress_payload
    company, user, _, device = account()
    other, other_user, _, _ = account("other")
    payload = {"entity_type": "device", "entity": {"external_id": device.external_id, "plan": "pro", "company_slug": other.slug, "assigned_username": user.username}}
    result = process_wordpress_payload(payload=payload, source="webhook")
    assert result["status"] == "error"
    device.refresh_from_db()
    assert device.company_id == company.pk
    payload["entity"]["assigned_username"] = other_user.username
    assert process_wordpress_payload(payload=payload, source="webhook")["status"] == "processed"
    device.refresh_from_db()
    assert device.company_id == other.pk and device.assigned_user_id == other_user.pk
