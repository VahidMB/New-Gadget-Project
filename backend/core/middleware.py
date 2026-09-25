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


class TransportSecurityMiddleware:
    """Use secure cookies on HTTPS while preserving loopback-only initial setup."""
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if request.is_secure():
            from django.conf import settings
            for name in [settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME]:
                if name in response.cookies:
                    response.cookies[name]["secure"] = True
        return response


class StaffAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from core.access import is_platform_owner, is_platform_user
        from core.staff_access import route_allowed, has_permission
        from django.core.exceptions import PermissionDenied
        if not request.user.is_authenticated or is_platform_owner(request.user):
            return None
        # Django admin must not bypass panel grants via is_staff or model permissions.
        if request.resolver_match.app_name == 'admin':
            raise PermissionDenied
        if not is_platform_user(request.user):
            return None
        name = request.resolver_match.url_name or ''
        if request.path.startswith('/panel/') and not route_allowed(request.user, name):
            raise PermissionDenied('این بخش در دسترسی‌های حساب شما فعال نشده است.')
        if name in {'health', 'wordpress-notifications'} and not has_permission(request.user, 'monitoring.view'):
            raise PermissionDenied
