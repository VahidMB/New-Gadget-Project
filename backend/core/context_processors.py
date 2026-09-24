from core.access import is_platform_owner, is_platform_user


def portal_permissions(request):
    return {
        "is_platform_user": is_platform_user(request.user),
        "is_platform_owner": is_platform_owner(request.user),
        "platform_config": getattr(request, "platform", None),
    }
