from prometheus_client import CollectorRegistry, Gauge, generate_latest

from core.models import DeviceStatus, ServiceHealth


def render_metrics() -> bytes:
    """Render current operational values without registering global collectors per request."""
    registry = CollectorRegistry()
    devices = Gauge("gadget_devices", "Devices by latest reported status", ["status"], registry=registry)
    services = Gauge("gadget_service_up", "Whether a service's last probe is up", ["service"], registry=registry)

    for status in DeviceStatus.STATUS_CHOICES:
        devices.labels(status=status[0]).set(DeviceStatus.objects.filter(status=status[0]).count())
    for service in ServiceHealth.objects.all():
        services.labels(service=service.service_name).set(int(service.status == "up"))
    return generate_latest(registry)