"""Write password hashes and per-device ACLs for the optional managed broker."""
import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from core.models import WordPressDevice, ResourceSnapshot
from core.runtime import integration, runtime_setting
from core.connections import broker_credential


def render(output):
    publisher = integration("mqtt")
    enabled = bool(publisher and publisher.is_active and publisher.username and publisher.secret())
    topic = runtime_setting("MQTT_TOPIC_ROOT")
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", topic) or (enabled and not re.fullmatch(r"[A-Za-z0-9_.-]+", publisher.username)):
        raise CommandError("Invalid MQTT topic or username")
    rows = [(publisher.username, publisher.secret())] if enabled else []
    acl = [f"user {publisher.username}", f"topic readwrite {topic}/#", ""] if enabled else []
    devices = WordPressDevice.objects.filter(is_active=True, customer_enabled=True, provisioning_state="provisioned").select_related("company", "assigned_user")
    if not enabled:
        devices = devices.none()
        acl = []
    for device in devices:
        if (device.company and not device.company.is_active) or (device.assigned_user and not device.assigned_user.is_active):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", device.external_id):
            continue
        username = f"device-{device.pk}"
        rows.append((username, broker_credential(device)))
        acl += [f"user {username}", f"topic read {topic}/devices/{device.external_id}/commands/#", f"topic read {topic}/devices/{device.external_id}/events/#", f"topic write {topic}/devices/{device.external_id}/telemetry/#", ""]
    if len({name for name, _ in rows}) != len(rows) or any("\n" in password or "\r" in password for _, password in rows):
        raise CommandError("Invalid or duplicate broker credential")
    plain = "".join(f"{name}:{password}\n" for name, password in rows)
    rules = "\n".join(acl)
    revision = hashlib.sha256((plain+rules).encode()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o755)
    if (output/"revision").exists() and (output/"revision").read_text() == revision:
        return len(rows)
    # Secrets never appear in argv or command output. Only hashes leave the private temp directory.
    with tempfile.TemporaryDirectory(dir=output) as folder:
        path = Path(folder)/"passwords"
        path.write_text(plain)
        path.chmod(0o600)
        if rows:
            subprocess.run(["mosquitto_passwd", "-U", str(path)], check=True, capture_output=True, timeout=15)
        if any(password in path.read_text() for _, password in rows):
            raise CommandError("Password hashing failed")
        path.chmod(0o644)
        os.replace(path, output/"passwords")
    for name, text in [("acl", rules), ("revision", revision)]:
        path = output/(name+".next")
        path.write_text(text)
        path.chmod(0o644)
        os.replace(path, output/name)
    return len(rows)


class Command(BaseCommand):
    help = "Apply owner-managed MQTT accounts and device ACLs without editing broker files."
    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--output", default="/managed")
    def handle(self, *args, **options):
        while True:
            try:
                count = render(Path(options["output"]))
                ResourceSnapshot.objects.update_or_create(service="broker-config", defaults={"origin": f"Applied {count} broker accounts"})
            except Exception as exc:
                if not options["loop"]:
                    raise CommandError(type(exc).__name__ + ": broker configuration failed") from None
                self.stderr.write(type(exc).__name__ + ": broker configuration failed; retrying")
            if not options["loop"]:
                break
            time.sleep(5)
