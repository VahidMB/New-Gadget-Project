from django.db.models import Q
from core.models import Company, CompanyMembership, WordPressDevice, ExternalDataSource, PlanRule


def is_platform_user(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or CompanyMembership.objects.filter(user=user, is_active=True, role__in=CompanyMembership.PLATFORM_ROLES).exists()))


def is_platform_owner(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or CompanyMembership.objects.filter(user=user, is_active=True, role="owner").exists()))


def managed_company_ids(user):
    if not user.is_authenticated or not user.is_active:
        return []
    if is_platform_user(user):
        return list(Company.objects.values_list("pk", flat=True))
    ids = set(CompanyMembership.objects.filter(user=user, is_active=True, company__is_active=True, role__in=["company_admin", "company_operator"]).values_list("company_id", flat=True))
    while ids:
        children = set(Company.objects.filter(parent_id__in=ids, is_active=True).values_list("pk", flat=True)) - ids
        if not children:
            break
        ids.update(children)
    return list(ids)


def visible_companies(user):
    if is_platform_user(user):
        return Company.objects.all()
    if not user.is_authenticated or not user.is_active:
        return Company.objects.none()
    return Company.objects.filter(Q(pk__in=managed_company_ids(user)) | Q(memberships__user=user, memberships__is_active=True), is_active=True).distinct()


def visible_devices(user):
    if is_platform_user(user):
        return WordPressDevice.objects.all()
    if not user.is_authenticated or not user.is_active:
        return WordPressDevice.objects.none()
    return WordPressDevice.objects.filter(company__is_active=True).filter(Q(company_id__in=managed_company_ids(user)) | Q(assigned_user=user, company__memberships__user=user, company__memberships__is_active=True)).distinct()


def scope_by_company(user, queryset, field_name="company"):
    if is_platform_user(user):
        return queryset
    if queryset.model is WordPressDevice:
        return queryset.filter(pk__in=visible_devices(user).values("pk"))
    return queryset.filter(**{f"{field_name}_id__in": managed_company_ids(user)})


def visible_sources(user):
    if is_platform_user(user):
        return ExternalDataSource.objects.all()
    return ExternalDataSource.objects.filter(Q(company__isnull=True) | Q(company_id__in=managed_company_ids(user)) | Q(created_by=user)).distinct()


def rule_for(plan):
    plan = "pro" if plan.lower() in {"pro", "vip", "premium", "professional"} else "simple"
    rule = PlanRule.objects.filter(plan_name=plan).first()
    if rule and not rule.is_active:
        return PlanRule(plan_name=plan, min_refresh_seconds=300)
    if rule:
        return rule
    return PlanRule(plan_name=plan, can_change_theme=True, can_customize_ui=plan == "pro", can_add_pages=plan == "pro", can_add_sources=plan == "pro", max_pages=5 if plan == "pro" else 3, max_elements_per_page=12, max_sources=5 if plan == "pro" else 0, max_telegram_sources=2 if plan == "pro" else 0, min_refresh_seconds=30 if plan == "pro" else 300, can_send_messages=plan == "pro")


def account_rule(company):
    has_pro = WordPressDevice.objects.filter(company_id__in=company_tree_ids(company.pk), plan__in=["pro", "vip", "premium", "professional"], is_active=True).exists()
    return rule_for("pro" if has_pro else "simple")


def can_manage_company(user, company):
    return is_platform_user(user) or company.pk in managed_company_ids(user)


def source_allowed(device, source):
    if not source.is_active:
        return False
    if source.company_id is None:
        return True
    if device.normalized_plan != "pro":
        return False
    # Private sources cannot cross ownership boundaries.
    return source.company_id in ancestor_company_ids(device.company_id) and (not source.created_by_id or source.created_by_id == device.assigned_user_id or source.created_by.company_memberships.filter(company_id=source.company_id, role__in=["company_admin", "company_operator"], is_active=True).exists())


def company_tree_ids(company_id):
    ids = {company_id}
    while True:
        extra = set(Company.objects.filter(parent_id__in=ids, is_active=True).values_list("pk", flat=True)) - ids
        if not extra:
            return ids
        ids.update(extra)


def ancestor_company_ids(company_id):
    ids = set()
    while company_id and company_id not in ids:
        ids.add(company_id)
        company_id = Company.objects.filter(pk=company_id, is_active=True).values_list("parent_id", flat=True).first()
    return ids
