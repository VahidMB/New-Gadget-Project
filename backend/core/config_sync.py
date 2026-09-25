"""Rebuild device configuration and durably track MQTT delivery."""

import logging

from django.db import transaction

from core.models import DeviceProfile, WordPressDevice
from core.services import _deep_merge, build_effective_display_config

logger = logging.getLogger(__name__)


def enqueue_config_notification(external_id, ui_version):
    from core.tasks import publish_device_config_changed

    try:
        publish_device_config_changed.apply_async(args=(external_id, ui_version), retry=False)
    except Exception:
        # Keep the database pending flag. Beat retries after broker recovery.
        logger.exception("Could not enqueue configuration for device %s", external_id)


def refresh_device_config(device_id, *, created=False):
    with transaction.atomic():
        device = WordPressDevice.objects.select_for_update().filter(pk=device_id).first()
        if device is None:
            return None
        custom = device.custom_config if isinstance(device.custom_config, dict) else {}
        profile = DeviceProfile.objects.filter(device_id=device_id).first()
        if profile:
            profile_custom = {
                "theme": {
                    "name": profile.theme_name,
                    "primary_color": profile.primary_color,
                    "secondary_color": profile.secondary_color,
                    "background_color": profile.background_color,
                },
                "layout_mode": profile.layout_mode,
                "refresh_interval_ms": profile.refresh_interval_ms,
            }
            if isinstance(profile.custom_config, dict):
                profile_custom = _deep_merge(profile_custom, profile.custom_config)
            custom = _deep_merge(custom, profile_custom)
        effective = build_effective_display_config(plan=device.plan, custom_config=custom)
        from core.models import DevicePreference
        from core.access import rule_for
        from core.content import device_content
        rule = rule_for(device.normalized_plan)
        preference = DevicePreference.objects.filter(device=device).first()
        if preference:
            palettes = {"navy": {"name": "navy", "primary_color": "#3885ff", "background_color": "#233b55", "secondary_color": "#ffffff"}, "light": {"name": "light", "primary_color": "#2865dd", "background_color": "#ffffff", "secondary_color": "#21354e"}, "carbon": {"name": "carbon", "primary_color": "#4499ff", "background_color": "#253747", "secondary_color": "#ffffff"}}
            if rule.can_change_theme:
                effective["theme"] = palettes.get(preference.theme, palettes["navy"]).copy()
            if rule.can_customize_ui and preference.custom_primary:
                effective.setdefault("theme", {})["primary_color"] = preference.custom_primary
            effective["rotation_seconds"] = preference.rotation_seconds
            effective["live_updates"] = preference.live_updates
        from core.buzzer import rules_config
        from core.connections import device_connection_config
        effective["buzzer"] = rules_config(device)
        effective["connections"] = device_connection_config(device)
        effective["data_refresh_seconds"] = max(5, rule.min_refresh_seconds)
        effective["selected_sources"] = [source["key"] for source in device_content(device)["sources"]]
        effective["rules"] = {"max_sources": rule.max_sources, "max_telegram_sources": rule.max_telegram_sources, "max_pages": rule.max_pages, "max_elements_per_page": rule.max_elements_per_page, "can_customize_ui": rule.can_customize_ui}
        if isinstance(effective.get("pages"), list):
            effective["pages"] = effective["pages"][:rule.max_pages]
            for page in effective["pages"]:
                if isinstance(page, dict) and isinstance(page.get("elements"), list):
                    page["elements"] = page["elements"][:rule.max_elements_per_page]
        if created or device.effective_config != effective:
            device.effective_config = effective
            if not created:
                device.ui_version += 1
            device.config_sync_pending = True
            WordPressDevice.objects.filter(pk=device_id).update(
                effective_config=effective,
                ui_version=device.ui_version,
                config_sync_pending=True,
            )
        if profile:
            DeviceProfile.objects.filter(pk=profile.pk).update(effective_config=effective)
        if device.config_sync_pending and device.is_active and device.provisioning_state == "provisioned":
            transaction.on_commit(lambda: enqueue_config_notification(device.external_id, device.ui_version))
        return device


def refresh_all_device_configs():
    for device_id in WordPressDevice.objects.values_list("pk", flat=True).iterator():
        refresh_device_config(device_id)
