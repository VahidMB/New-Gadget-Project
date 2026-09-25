from core.access import is_platform_owner, is_platform_user


def portal_permissions(request):
    from core.staff_access import route_allowed
    menu = [('panel-device-list', 'گجت‌ها و نمایندگان'), ('panel-price-list', 'لیست قیمت شرکت'),
            ('panel-data-source-list', 'منابع اطلاعات'), ('panel-message-list', 'پیام‌ها و زمان‌بندی'),
            ('panel-company-list', 'شرکت‌ها'), ('panel-user-list', 'کاربران'),
            ('panel-firmware-list', 'نسخه نرم‌افزار'), ('panel-templates', 'تم‌ها و صفحات'),
            ('panel-rules', 'پلن‌ها و سهمیه‌ها'), ('panel-monitoring', 'پایش و لاگ‌ها'),
            ('panel-connections', 'ارتباطات سرور و گجت'), ('panel-integrations', 'اتصال‌ها و توکن‌ها'),
            ('panel-settings', 'تنظیمات سامانه')]
    return {
        'staff_menu': [{'route': route, 'label': label} for route, label in menu if route_allowed(request.user, route)],
        "is_platform_user": is_platform_user(request.user),
        "is_platform_owner": is_platform_owner(request.user),
        "platform_config": getattr(request, "platform", None),
    }
