from django.urls import path

from core.views import device_display_config, device_heartbeat, health, wordpress_notifications, wordpress_pull_sync, wordpress_webhook

urlpatterns = [
    path("health/", health, name="health"),
    path("integrations/wordpress/webhook/", wordpress_webhook, name="wordpress-webhook"),
    path("integrations/wordpress/sync/", wordpress_pull_sync, name="wordpress-sync"),
    path("integrations/wordpress/notifications/", wordpress_notifications, name="wordpress-notifications"),
    path("devices/<str:external_id>/display-config/", device_display_config, name="device-display-config"),
    path("devices/<str:external_id>/heartbeat/", device_heartbeat, name="device-heartbeat"),
