from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os
from django.conf import settings
from core.models import Integration
from core.runtime import platform_settings
from core.secrets import setup_code


class Command(BaseCommand):
    help = "Initialize the setup record and print the first-run claim code when needed."
    def handle(self, *args, **options):
        config = platform_settings()
        if not config.setup_complete:
            config.test_mode = os.getenv("GADGET_TEST_MODE", "0") == "1"
            config.save(update_fields=["test_mode"])
        defaults = [
            ("mqtt", "MQTT", "mqtt", settings.MQTT_HOST, settings.MQTT_USERNAME, settings.MQTT_PASSWORD),
            ("wordpress", "WordPress", "wordpress", settings.WORDPRESS_API_BASE_URL, "", settings.WORDPRESS_API_TOKEN),
            ("wordpress-sync", "فراخوان همگام‌سازی وردپرس", "wordpress", "", "", settings.WORDPRESS_SYNC_TRIGGER_TOKEN),
            ("notifications", "اعلان‌ها", "notifications", settings.SYNC_NOTIFY_WEBHOOK_URL, "", ""),
            ("metrics", "توکن آمار", "metrics", "", "", settings.METRICS_TOKEN),
        ]
        for key, name, kind, endpoint, username, secret in defaults:
            obj, created = Integration.objects.get_or_create(key=key, defaults={"name": name, "kind": kind, "endpoint": endpoint, "username": username})
            if not created:
                continue
            if key == "mqtt" and os.getenv("GADGET_MANAGED_BROKER") == "1":
                import secrets
                obj.username = "gadget-backend"
                secret = secrets.token_urlsafe(32)
            obj.set_secret(secret)
            if key == "mqtt":
                obj.port, obj.use_tls = settings.MQTT_PORT, settings.MQTT_USE_TLS
                obj.options = {"topic_root": settings.MQTT_TOPIC_ROOT}
            if key == "wordpress":
                obj.set_secret(settings.WORDPRESS_WEBHOOK_SECRET, webhook=True)
                obj.options = {"devices_endpoint": settings.WORDPRESS_DEVICES_ENDPOINT, "sources_endpoint": settings.WORDPRESS_DATA_SOURCES_ENDPOINT}
            obj.save()
        if not config.setup_complete and not get_user_model().objects.filter(is_superuser=True).exists():
            self.stdout.write("Open /setup/ in your browser. First-run setup code:")
            self.stdout.write(setup_code())
        else:
            self.stdout.write("Platform already initialized.")
