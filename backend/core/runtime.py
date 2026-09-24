"""Application integrations are editable at runtime by the platform owner."""
from django.conf import settings
from core.models import Integration, PlatformSettings


def platform_settings():
    return PlatformSettings.objects.get_or_create(pk=1)[0]


def integration(key):
    return Integration.objects.filter(key=key, company__isnull=True).first()


def runtime_setting(name):
    mapping = {
        "WORDPRESS_API_BASE_URL": ("wordpress", "endpoint"),
        "WORDPRESS_API_TOKEN": ("wordpress", "secret"),
        "WORDPRESS_WEBHOOK_SECRET": ("wordpress", "webhook"),
        "WORDPRESS_SYNC_TRIGGER_TOKEN": ("wordpress-sync", "secret"),
        "SYNC_NOTIFY_WEBHOOK_URL": ("notifications", "endpoint"),
        "METRICS_TOKEN": ("metrics", "secret"),
        "MQTT_HOST": ("mqtt", "endpoint"), "MQTT_PORT": ("mqtt", "port"),
        "MQTT_USERNAME": ("mqtt", "username"), "MQTT_PASSWORD": ("mqtt", "secret"),
        "MQTT_USE_TLS": ("mqtt", "use_tls"),
    }
    options_map = {"WORDPRESS_DEVICES_ENDPOINT": ("wordpress", "devices_endpoint"), "WORDPRESS_DATA_SOURCES_ENDPOINT": ("wordpress", "sources_endpoint"), "MQTT_TOPIC_ROOT": ("mqtt", "topic_root")}
    if name in options_map:
        key, option = options_map[name]
        record = integration(key)
        return record.options.get(option, getattr(settings, name)) if record else getattr(settings, name)
    if name not in mapping:
        return getattr(settings, name)
    key, field = mapping[name]
    record = integration(key)
    if record is None:
        return getattr(settings, name)
    if not record.is_active:
        return "" if field not in {"port", "use_tls"} else getattr(settings, name)
    if field == "secret":
        return record.secret()
    if field == "webhook":
        return record.secret(webhook=True)
    return getattr(record, field)
