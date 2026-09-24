from zoneinfo import ZoneInfo
from django.utils import timezone
from django.db.utils import OperationalError, ProgrammingError
from core.models import PlatformSettings


class PlatformMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        try:
            config = PlatformSettings.objects.filter(pk=1).first()
            request.platform = config
            timezone.activate(ZoneInfo(config.timezone if config else "Asia/Tehran"))
        except (OperationalError, ProgrammingError):
            request.platform = None
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
