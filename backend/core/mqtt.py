"""Small, failure-safe MQTT publishing boundary for device commands."""

from __future__ import annotations

import json

import paho.mqtt.publish as publish
from django.conf import settings


def device_topic(external_id: str, suffix: str) -> str:
    return f"{settings.MQTT_TOPIC_ROOT}/devices/{external_id}/{suffix}"


def publish_device_message(*, external_id: str, suffix: str, payload: dict) -> None:
    """Publish a retained JSON command to one device's private topic."""
    auth = None
    if settings.MQTT_USERNAME:
        auth = {"username": settings.MQTT_USERNAME, "password": settings.MQTT_PASSWORD}
    tls = {} if settings.MQTT_USE_TLS else None
    publish.single(
        topic=device_topic(external_id, suffix),
        payload=json.dumps(payload, separators=(",", ":")),
        qos=1,
        retain=True,
        hostname=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        auth=auth,
        tls=tls,
    )