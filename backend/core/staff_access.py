"""Explicit, deny-by-default permissions for platform employees."""
from core.access import is_platform_owner, is_platform_user

RESOURCES = {
    'devices': 'گجت‌ها، محتوای دستگاه و سوابق بازر',
    'sources': 'منابع اطلاعات', 'prices': 'لیست قیمت‌ها', 'messages': 'پیام‌ها و زمان‌بندی',
    'companies': 'شرکت‌ها', 'users': 'کاربران عادی', 'firmware': 'نسخه‌های نرم‌افزار',
    'templates': 'تم‌ها و صفحات',
}
CHOICES = [(f'{key}.view', f'مشاهده {label}') for key, label in RESOURCES.items()]
CHOICES += [(f'{key}.manage', f'مدیریت {label}') for key, label in RESOURCES.items() if key not in {'users', 'firmware'}]
CHOICES += [('users.create', 'افزودن کاربر عادی'), ('users.edit', 'ویرایش و غیرفعال‌سازی کاربران عادی'),
            ('firmware.upload', 'بارگذاری و انتشار نسخه نرم‌افزار'), ('monitoring.view', 'پایش سرویس‌ها و مشاهده لاگ‌های مدیریت'),
            ('monitoring.check', 'اجرای بررسی سرویس‌ها'), ('plans.manage', 'مدیریت پلن‌ها و سهمیه‌ها'),
            ('connections.manage', 'تغییر ارتباطات سرور و دستگاه‌ها'), ('integrations.manage', 'مدیریت اتصال‌ها و توکن‌های محرمانه'),
            ('settings.manage', 'تغییر تنظیمات سامانه')]

ROUTES = {}
def routes(permission, names):
    for name in names.split():
        ROUTES['panel-' + name] = permission

routes('devices.view', 'device-list device-detail live live-stream buzzer-list buzzer-history')
routes('devices.manage', 'device-create device-edit preferences device-activation-toggle device-bulk buzzer-create buzzer-edit')
routes('sources.view', 'data-source-list')
routes('sources.manage', 'data-source-create data-source-edit source-refresh')
routes('prices.view', 'price-list price-detail')
routes('prices.manage', 'price-create price-edit price-item-create price-item-edit')
routes('messages.view', 'message-list')
routes('messages.manage', 'message-create message-edit')
routes('companies.view', 'company-list')
routes('companies.manage', 'company-create company-edit')
routes('users.view', 'user-list')
routes('users.create', 'user-create')
routes('users.edit', 'user-edit')
routes('firmware.view', 'firmware-list')
routes('firmware.upload', 'firmware-upload')
routes('templates.view', 'templates template-detail')
routes('templates.manage', 'template-create template-edit page-create page-edit element-create element-edit')
routes('monitoring.view', 'monitoring')
routes('monitoring.check', 'monitor-check')
routes('plans.manage', 'rules rule-edit')
routes('connections.manage', 'connections')
routes('integrations.manage', 'integrations integration-create integration-edit')
routes('settings.manage', 'settings')
# Memberships, grants, provisioning and credential rotation remain owner-only.
OWNER_ROUTES = {'panel-membership-list', 'panel-membership-create', 'panel-membership-edit',
                'panel-user-access', 'panel-device-token-rotate', 'panel-device-token-success', 'panel-broker-rotate'}


def has_permission(user, permission):
    if is_platform_owner(user):
        return True
    if not is_platform_user(user):
        return False
    from core.models import StaffAccess
    grants = StaffAccess.objects.filter(user=user).values_list('permissions', flat=True).first() or []
    if permission in grants:
        return True
    # Write access includes viewing the same section, never another write action.
    return permission.endswith('.view') and any(p.startswith(permission[:-4]) for p in grants)


def route_allowed(user, name):
    if is_platform_owner(user):
        return True
    if name in OWNER_ROUTES:
        return False
    if not is_platform_user(user):
        return True  # Existing customer/company checks remain authoritative.
    if name == 'panel-dashboard':
        return True
    return bool(name in ROUTES and has_permission(user, ROUTES[name]))


def delegated_route_allowed(request):
    name = request.resolver_match.url_name if request.resolver_match else None
    return is_platform_user(request.user) and name in ROUTES and route_allowed(request.user, name)
