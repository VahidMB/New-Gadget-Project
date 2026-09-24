"""Small, failure-safe MQTT publishing boundary for device commands."""

from __future__ import annotations

import json

import paho.mqtt.publish as publish
from core.runtime import runtime_setting


def device_topic(external_id: str, suffix: str) -> str:
    return f"{runtime_setting("MQTT_TOPIC_ROOT")}/devices/{external_id}/{suffix}"


def publish_device_message(*, external_id: str, suffix: str, payload: dict, retain: bool = True) -> None:
    """Publish a retained JSON command to one device's private topic."""
    auth = None
    if runtime_setting("MQTT_USERNAME"):
        auth = {"username": runtime_setting("MQTT_USERNAME"), "password": runtime_setting("MQTT_PASSWORD")}
    tls = {} if runtime_setting("MQTT_USE_TLS") else None
    publish.single(
        topic=device_topic(external_id, suffix),
        payload=json.dumps(payload, separators=(",", ":")),
        qos=1,
        retain=retain,
        hostname=runtime_setting("MQTT_HOST"),
        port=runtime_setting("MQTT_PORT"),
        auth=auth,
        tls=tls,
    )