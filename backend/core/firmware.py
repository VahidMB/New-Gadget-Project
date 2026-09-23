"""Choose only stable firmware versions newer than the reported version."""

from django.db.models import Q
from django.utils import timezone
from packaging.version import InvalidVersion, Version

from core.models import FirmwareRelease


def select_firmware_release(hardware_model: str, current_version: str):
    try:
        current = Version(current_version) if current_version else None
    except InvalidVersion:
        # An unknown version cannot be safely ordered: never guess a downgrade.
        return None

    candidates = []
    for release in FirmwareRelease.objects.filter(
        hardware_model=hardware_model, is_active=True
    ).filter(Q(published_at__isnull=True) | Q(published_at__lte=timezone.now())):
        try:
            version = Version(release.version)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        if current is None or version > current:
            candidates.append((version, release.pk, release))
    return max(candidates, default=(None, None, None), key=lambda item: item[:2])[2]
