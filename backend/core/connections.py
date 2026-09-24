"""Public device connection contract; credentials are returned only by authenticated bootstrap."""
from urllib.parse import urlsplit
from core.runtime import platform_settings, runtime_setting
from core.models import DeviceBrokerCredential
from core.secrets import encrypt, decrypt
import secrets


def device_connection_config(device):
    config = platform_settings()
    base = config.public_base_url.rstrip("/")
    topic = runtime_setting("MQTT_TOPIC_ROOT")
    return {"api_base_url": base + "/api/v1/" if base else "/api/v1/", "heartbeat_seconds": config.device_heartbeat_seconds,
            "mqtt": {"host": config.device_mqtt_host or urlsplit(base).hostname or "", "port": config.device_mqtt_port, "transport": config.device_mqtt_transport, "tls": config.device_mqtt_tls, "path": config.device_mqtt_path, "username": f"device-{device.pk}", "subscribe": [f"{topic}/devices/{device.external_id}/commands/#", f"{topic}/devices/{device.external_id}/events/#"]},
            "bootstrap_path": f"/api/v1/devices/{device.external_id}/connections/"}


def broker_credential(device, rotate=False):
    obj, created = DeviceBrokerCredential.objects.get_or_create(device=device, defaults={"encrypted_password": encrypt(secrets.token_urlsafe(32))})
    if rotate:
        obj.encrypted_password = encrypt(secrets.token_urlsafe(32))
        obj.save()
    return decrypt(obj.encrypted_password)
