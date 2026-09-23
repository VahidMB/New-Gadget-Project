import hashlib
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.migrations.loader import MigrationLoader
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from core.config_sync import enqueue_config_notification
from core.device_auth import generate_device_token
from core.forms import FirmwareUploadForm
from core.models import (
    Company, CompanyMembership, DeviceProfile, FirmwareRelease, SyncNotification,
    UIElement, UIPage, UITemplate, WordPressDevice,
)
from core.services import process_wordpress_payload
from core.tasks import publish_device_config_changed, retry_pending_config_notifications


def device_client(**kwargs):
    token, token_hash = generate_device_token()
    device = WordPressDevice.objects.create(
        external_id="regression-device", hardware_model="esp32-s3",
        provisioning_state="provisioned", device_token_hash=token_hash, **kwargs,
    )
    client = APIClient()
    client.credentials(HTTP_X_DEVICE_TOKEN=token)
    return device, client


def release(version, **kwargs):
    return FirmwareRelease.objects.create(
        hardware_model="esp32-s3", version=version,
        download_url="https://firmware.example.test/image.bin",
        checksum_sha256="a" * 64, **kwargs,
    )


def test_core_migrations_are_discovered():
    loader = MigrationLoader(None)
    assert ("core", "0001_initial") in loader.disk_migrations
    assert ("core", "0008_device_config_delivery") in loader.disk_migrations


@pytest.mark.parametrize("current", ["2.0.0", "3.0.0", "custom-build"])
def test_ota_never_downgrades_or_guesses_an_unknown_version(current):
    device, client = device_client()
    release("1.0.0")
    release("2.0.0")
    response = client.get(f"/api/v1/devices/{device.external_id}/firmware/update-check/", {"firmware_version": current})
    assert response.status_code == 200
    assert response.json()["update_available"] is False
    assert not device.firmware_deployments.exists()


def test_ota_uses_version_order_and_excludes_future_inactive_and_preview_releases():
    device, client = device_client()
    release("1.10.0")
    release("1.9.0")
    release("9.0.0", published_at=timezone.now() + timedelta(days=1))
    release("8.0.0", is_active=False)
    release("7.0.0rc1")
    release("not-a-version")
    response = client.get(f"/api/v1/devices/{device.external_id}/firmware/update-check/", {"firmware_version": "1.8.0"})
    assert response.json()["version"] == "1.10.0"


def test_notifications_are_private_to_platform_users():
    SyncNotification.objects.create(category="test", title="Private", message="Private data")
    client = APIClient()
    url = "/api/v1/integrations/wordpress/notifications/"
    assert client.get(url).status_code == 403
    user = get_user_model().objects.create_user(username="company-user")
    company = Company.objects.create(name="Company", slug="company")
    membership = CompanyMembership.objects.create(user=user, company=company, role="company_admin")
    client.force_authenticate(user)
    assert client.get(url).status_code == 403
    membership.company = None
    membership.role = "employee"
    membership.save()
    assert client.get(url).json()["count"] == 1
    for limit in ["bad", "-1", "0", "201"]:
        assert client.get(url, {"limit": limit}).status_code == 400


def test_firmware_form_requires_a_file_without_crashing():
    form = FirmwareUploadForm({"hardware_model": "esp32-s3", "version": "1.0.0"})
    assert not form.is_valid()
    assert "firmware_file" in form.errors


def test_firmware_upload_hash_and_size_validation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    content = b"test firmware bytes"
    form = FirmwareUploadForm(
        {"hardware_model": "esp32-s3", "version": "1.0.0", "is_active": True},
        {"firmware_file": SimpleUploadedFile("firmware.bin", content)},
    )
    assert form.is_valid(), form.errors
    uploaded = form.save()
    assert uploaded.checksum_sha256 == hashlib.sha256(content).hexdigest()
    settings.MAX_FIRMWARE_UPLOAD_BYTES = 2
    form = FirmwareUploadForm(
        {"hardware_model": "esp32-s3", "version": "2.0.0"},
        {"firmware_file": SimpleUploadedFile("large.bin", content)},
    )
    assert not form.is_valid()
    assert "firmware_file" in form.errors


def test_panel_plan_edit_rebuilds_config_and_notifies_after_commit(django_capture_on_commit_callbacks):
    device, _ = device_client(plan="simple")
    owner = get_user_model().objects.create_user(username="owner", is_superuser=True)
    client = Client()
    client.force_login(owner)
    with patch("core.tasks.publish_device_config_changed.apply_async") as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(f"/panel/devices/{device.pk}/edit/", {
                "external_id": device.external_id, "hardware_model": device.hardware_model,
                "plan": "pro", "is_active": "on",
            })
            enqueue.assert_not_called()
        assert response.status_code == 302
        device.refresh_from_db()
        assert device.effective_config["plan"] == "pro"
        assert device.ui_version == 2
        assert device.config_sync_pending
        enqueue.assert_called_once_with(args=(device.external_id, 2), retry=False)


def test_profile_template_and_element_changes_rebuild_existing_devices():
    device = WordPressDevice.objects.create(external_id="pro", plan="professional")
    assert device.normalized_plan == "pro"
    template = UITemplate.objects.create(name="Template", plan_type="pro")
    page = UIPage.objects.create(template=template, page_key="home", page_type="dashboard")
    element = UIElement.objects.create(page=page, element_type="text", label="Before")
    device.refresh_from_db()
    revision = device.ui_version
    element.label = "After"
    element.save()
    device.refresh_from_db()
    assert device.ui_version == revision + 1
    assert device.effective_config["pages"][0]["elements"][0]["label"] == "After"
    profile = DeviceProfile.objects.create(device=device, primary_color="#123456")
    device.refresh_from_db()
    profile.refresh_from_db()
    assert device.effective_config["theme"]["primary_color"] == "#123456"
    assert profile.effective_config == device.effective_config
    profile.delete()
    device.refresh_from_db()
    assert device.effective_config["theme"]["primary_color"] == "#00B7FF"
    template.delete()
    device.refresh_from_db()
    assert "pages" not in device.effective_config


def test_simple_plan_ignores_profile_customization():
    device = WordPressDevice.objects.create(external_id="simple", plan="simple")
    original = device.effective_config
    DeviceProfile.objects.create(device=device, primary_color="#123456", custom_config={"screens": []})
    device.refresh_from_db()
    assert device.effective_config == original
    assert device.ui_version == 1


def test_wordpress_update_increments_revision_once_and_noop_does_not():
    device = WordPressDevice.objects.create(external_id="wp", plan="simple")
    payload = {"entity_type": "device", "entity": {"external_id": "wp", "plan": "pro"}}
    process_wordpress_payload(payload=payload, source="webhook")
    device.refresh_from_db()
    assert device.ui_version == 2
    process_wordpress_payload(payload=payload, source="webhook")
    device.refresh_from_db()
    assert device.ui_version == 2


def test_broker_outage_keeps_pending_notification_for_periodic_recovery():
    device, _ = device_client()
    with patch("core.tasks.publish_device_config_changed.apply_async", side_effect=OSError("offline")):
        enqueue_config_notification(device.external_id, device.ui_version)
    device.refresh_from_db()
    assert device.config_sync_pending
    with patch("core.tasks.publish_device_config_changed.apply_async") as enqueue:
        assert retry_pending_config_notifications() == 1
        enqueue.assert_called_once()
    with patch("core.tasks.publish_device_message") as publish:
        publish_device_config_changed(device.external_id, 0)
        assert publish.call_args.kwargs["payload"]["ui_version"] == device.ui_version
    device.refresh_from_db()
    assert not device.config_sync_pending


def test_new_revision_during_publish_stays_pending(monkeypatch):
    device, _ = device_client()
    def update_while_publishing(**kwargs):
        WordPressDevice.objects.filter(pk=device.pk).update(ui_version=2, config_sync_pending=True)
    monkeypatch.setattr("core.tasks.publish_device_message", Mock(side_effect=update_while_publishing))
    publish_device_config_changed(device.external_id, 1)
    device.refresh_from_db()
    assert device.config_sync_pending


def test_suspended_device_never_receives_config_notification():
    device = WordPressDevice.objects.create(external_id="suspended", provisioning_state="suspended")
    with patch("core.tasks.publish_device_message") as publish:
        publish_device_config_changed(device.external_id, device.ui_version)
        publish.assert_not_called()
