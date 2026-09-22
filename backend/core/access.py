from django.db.models import QuerySet

from core.models import Company, CompanyMembership


def is_platform_user(user) -> bool:
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or CompanyMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=CompanyMembership.PLATFORM_ROLES,
            ).exists()
        )
    )


def is_platform_owner(user) -> bool:
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or CompanyMembership.objects.filter(
                user=user,
                is_active=True,
                role=CompanyMembership.Role.OWNER,
            ).exists()
        )
    )


def visible_companies(user) -> QuerySet[Company]:
    if is_platform_user(user):
        return Company.objects.filter(is_active=True)
    return Company.objects.filter(memberships__user=user, memberships__is_active=True, is_active=True).distinct()


def scope_by_company(user, queryset: QuerySet, field_name: str = "company") -> QuerySet:
    if is_platform_user(user):
        return queryset
    return queryset.filter(**{f"{field_name}__in": visible_companies(user)})
