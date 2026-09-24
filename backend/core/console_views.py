import secrets
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import (is_platform_user, is_platform_owner, visible_companies, visible_devices, visible_sources, managed_company_ids, rule_for, account_rule, source_allowed, company_tree_ids)
from core.models import (Company, WordPressDevice, ExternalDataSource, SourceSelection, DevicePreference, PriceList, PriceItem, MessageCampaign, Integration, PlatformSettings, PlanRule, UITemplate, UIPage, UIElement, ServiceHealth, ResourceSnapshot, AuditEvent)
from core.platform_forms import (CompanyEditForm, DeviceEditForm, SourceForm, PreferenceForm, IntegrationForm, SettingsForm, RuleForm, TemplateForm, PageForm, ElementForm, PriceListForm, PriceItemForm, CampaignForm, UserEditForm, SetupForm)
from core.runtime import platform_settings
from core.source_engine import read_value, refresh_source
from core.content import device_content, purge_expired_content


def owner_only(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not is_platform_owner(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def audit(request, action, obj):
    AuditEvent.objects.create(actor=request.user, action=action, object_label=str(obj)[:180])


def form_page(request, form, title, back="panel-dashboard", **context):
    return render(request, "core/portal/editor.html", {"form": form, "heading": title, "cancel_url": back, **context})


def list_page(request, title, columns, rows, create=None, note=""):
    page = Paginator(rows, 30).get_page(request.GET.get("page"))
    return render(request, "core/portal/listing.html", {"heading": title, "columns": columns, "rows": page, "create_url": create, "note": note, "bulk_devices": request.resolver_match.url_name == "panel-device-list"})


def manage_company(request, company):
    if not is_platform_user(request.user) and company.pk not in managed_company_ids(request.user):
        raise PermissionDenied
    if not is_platform_user(request.user) and not account_rule(company).can_send_messages:
        raise PermissionDenied("ارسال و مدیریت گروهی به پلن Pro نیاز دارد.")


def device_state(device):
    if not device.is_active or device.provisioning_state == "suspended":
        return "تعلیق توسط مدیر", "danger"
    if not device.customer_enabled:
        return "غیرفعال", "muted"
    status = getattr(device, "status", None)
    timeout = platform_settings().heartbeat_timeout
    if status and status.last_heartbeat_at and status.last_heartbeat_at > timezone.now() - timedelta(seconds=timeout):
        if status.status == "online":
            return "آنلاین", "success"
        if status.status == "updating":
            return "در حال آپدیت", "warning"
        if status.status == "error":
            return "نیازمند بررسی", "danger"
    return "قطع ارتباط", "warning"


@login_required
def dashboard(request):
    devices = visible_devices(request.user).select_related("company", "assigned_user", "status")
    selected = devices.filter(pk=request.GET.get("device")).first() if request.GET.get("device", "").isdigit() else devices.first()
    for device in devices:
        device.connection_label, device.connection_style = device_state(device)
    if is_platform_user(request.user):
        users = get_user_model().objects.filter(is_superuser=False).exclude(company_memberships__role__in=["owner", "employee"]).distinct()
        vip_ids = WordPressDevice.objects.filter(plan__in=["pro", "vip", "premium", "professional"], assigned_user__isnull=False).values_list("assigned_user_id", flat=True)
        vip = users.filter(pk__in=vip_ids).count()
        context = {"heading": "داشبورد مدیریت", "devices": devices[:8], "total_devices": devices.count(), "online_count": sum(d.connection_style == "success" for d in devices), "vip_count": vip, "simple_count": users.count()-vip, "company_count": Company.objects.filter(account_kind="business").count(), "services": service_cards(), "recent_events": AuditEvent.objects.select_related("actor")[:5], "sources_failed": ExternalDataSource.objects.exclude(last_error="").count()}
        return render(request, "core/portal/admin_dashboard.html", context)
    content = device_content(selected) if selected else {"sources": [], "price_lists": [], "messages": []}
    context = {"heading": "قیمت‌ها و اطلاعات من", "devices": devices, "selected_device": selected, "content": content, "price_sources": [s for s in content["sources"] if s["category"] == "price"], "other_sources": [s for s in content["sources"] if s["category"] != "price"], "is_business": devices.count() > 1, "rule": rule_for(selected.normalized_plan) if selected else rule_for("simple")}
    if selected:
        context["connection_label"], context["connection_style"] = device_state(selected)
        context["preference"] = DevicePreference.objects.filter(device=selected).first()
    return render(request, "core/portal/customer_dashboard.html", context)


@login_required
def dashboard_data(request):
    device_id = request.GET.get("device", "")
    if not device_id.isdigit():
        return JsonResponse({"detail": "Invalid device"}, status=400)
    device = get_object_or_404(visible_devices(request.user), pk=device_id)
    data = device_content(device)
    data["connection"] = device_state(device)[0]
    response = JsonResponse(data)
    response["Cache-Control"] = "no-store"
    return response


@login_required
def device_list(request):
    devices = visible_devices(request.user).select_related("company", "assigned_user", "status")
    query = request.GET.get("q", "")[:100]
    if query:
        devices = devices.filter(Q(name__icontains=query) | Q(recipient_name__icontains=query) | Q(external_id__icontains=query) | Q(group_name__icontains=query))
    rows = []
    for device in devices:
        label, style = device_state(device)
        rows.append({"pk": device.pk, "cells": [device.name or device.external_id, str(device.company or "—"), device.recipient_name or (str(device.assigned_user) if device.assigned_user else "آماده تخصیص"), device.group_name or "—", "VIP" if device.normalized_plan == "pro" else "ساده", label], "url": reverse("panel-device-detail", args=[device.pk]), "badge": style})
    return list_page(request, "گجت‌ها و نمایندگان", ["گجت", "حساب مالک", "استفاده‌کننده", "گروه", "پلن", "وضعیت"], rows, reverse("panel-device-create") if is_platform_owner(request.user) else None)


@login_required
def device_detail(request, pk):
    device = get_object_or_404(visible_devices(request.user).select_related("company", "assigned_user", "status"), pk=pk)
    label, style = device_state(device)
    return render(request, "core/portal/device_overview.html", {"device": device, "connection_label": label, "connection_style": style, "content": device_content(device), "can_control": is_platform_owner(request.user) or (device.normalized_plan == "pro" and device.company_id in managed_company_ids(request.user))})


@owner_only
def device_create(request):
    form = DeviceEditForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            device = form.save()
            audit(request, "device.create", device)
        return redirect("panel-device-detail", pk=device.pk)
    return form_page(request, form, "افزودن گجت", "panel-device-list")


@login_required
def device_edit(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    form = DeviceEditForm(request.POST or None, instance=device)
    if not is_platform_user(request.user):
        editable = {"name"}
        if device.company_id in managed_company_ids(request.user) and device.normalized_plan == "pro":
            editable |= {"recipient_name", "recipient_contact", "assigned_user", "group_name", "customer_enabled"}
        for name in list(form.fields):
            if name not in editable:
                form.fields.pop(name)
    if "assigned_user" in form.fields and not is_platform_user(request.user):
        form.fields["assigned_user"].queryset = get_user_model().objects.filter(company_memberships__company=device.company, company_memberships__is_active=True).distinct()
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            audit(request, "device.edit", device)
        messages.success(request, "تغییرات گجت ذخیره شد.")
        return redirect("panel-device-detail", pk=pk)
    return form_page(request, form, "ویرایش گجت", "panel-device-list")


@login_required
@require_POST
def device_activation_toggle(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    if is_platform_owner(request.user):
        device.is_active = not device.is_active
        device.provisioning_state = "suspended" if not device.is_active else ("provisioned" if device.device_token_hash else "unprovisioned")
    else:
        if device.normalized_plan != "pro" or device.company_id not in managed_company_ids(request.user):
            raise PermissionDenied
        if not device.is_active or device.provisioning_state == "suspended":
            raise PermissionDenied("تعلیق ادمین توسط مشتری قابل لغو نیست.")
        device.customer_enabled = not device.customer_enabled
    with transaction.atomic():
        device.save()
        audit(request, "device.activation", device)
    return redirect("panel-device-detail", pk=pk)


@login_required
def preferences(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    preference = DevicePreference.objects.filter(device=device).first() or DevicePreference(device=device)
    rule = rule_for(device.normalized_plan)
    form = PreferenceForm(request.POST or None, instance=preference)
    allowed = [s.pk for s in visible_sources(request.user).filter(is_active=True) if source_allowed(device, s)]
    form.fields["sources"].queryset = ExternalDataSource.objects.filter(pk__in=allowed)
    if request.method != "POST":
        initial = list(device.source_selections.filter(enabled=True).values_list("source_id", flat=True))
        form.fields["sources"].initial = initial
        form.fields["ordered_sources"].initial = ",".join(map(str, initial))
    if not rule.can_customize_ui and not is_platform_user(request.user):
        form.fields.pop("custom_primary")
    if not rule.can_change_theme and not is_platform_user(request.user):
        form.fields.pop("theme")
    if request.method == "POST" and form.is_valid():
        selected = form.cleaned_data["sources"]
        private = selected.filter(company__isnull=False)
        if not is_platform_user(request.user) and (private.exclude(source_type="telegram").count() > rule.max_sources or private.filter(source_type="telegram").count() > rule.max_telegram_sources):
            form.add_error("sources", "تعداد منابع انتخابی از سهمیه پلن بیشتر است.")
        else:
            with transaction.atomic():
                WordPressDevice.objects.select_for_update().get(pk=pk)
                preference = form.save()
                SourceSelection.objects.filter(device=device).exclude(source__in=selected).delete()
                order = form.cleaned_data.get("ordered_sources", "").split(",")
                ordered = sorted(selected, key=lambda s: order.index(str(s.pk)) if str(s.pk) in order else len(order))
                for position, source in enumerate(ordered):
                    SourceSelection.objects.update_or_create(device=device, source=source, defaults={"enabled": True, "position": position})
                from core.config_sync import refresh_device_config
                refresh_device_config(pk)
                audit(request, "device.preferences", device)
            messages.success(request, "اطلاعات و ظاهر انتخاب‌شده ذخیره شد.")
            return redirect("panel-dashboard")
    return form_page(request, form, "محتوا، ظاهر و زمان‌بندی", note=f"دریافت داده: حداقل هر {rule.min_refresh_seconds} ثانیه. این مقدار مستقل از زمان تعویض محتواست.")


@login_required
def data_source_list(request):
    rows = []
    for source in visible_sources(request.user).select_related("company"):
        value = read_value(source)
        rows.append({"cells": [source.name, source.get_source_type_display(), str(source.company or "کتابخانه عمومی"), value["value"] if value else "در انتظار به‌روزرسانی", source.unit, "به‌روز" if value else ("خطای دریافت" if source.last_error else "در انتظار")], "url": reverse("panel-data-source-edit", args=[source.pk]) if is_platform_user(request.user) or source.company_id in managed_company_ids(request.user) or source.created_by_id == request.user.pk else ""})
    return list_page(request, "منابع اطلاعات", ["منبع", "نوع", "مالک", "آخرین مقدار معتبر", "واحد", "وضعیت"], rows, reverse("panel-data-source-create"), "منابع عمومی توسط مدیر تعریف می‌شوند. مقادیر منقضی‌شده نمایش داده نمی‌شوند.")


@login_required
def source_editor(request, pk=None):
    source = get_object_or_404(visible_sources(request.user), pk=pk) if pk else ExternalDataSource()
    if pk and not is_platform_user(request.user) and (source.company_id is None or (source.company_id not in managed_company_ids(request.user) and source.created_by_id != request.user.pk)):
        raise PermissionDenied
    form = SourceForm(request.POST or None, instance=source)
    companies = visible_companies(request.user)
    form.fields["company"].queryset = companies
    if not is_platform_user(request.user):
        form.fields["company"].required = True
        form.fields.pop("credential_reference")
        form.fields["source_type"].choices = [c for c in form.fields["source_type"].choices if c[0] != "internal"]
        if companies.count() == 1:
            form.fields["company"].initial = companies.first()
    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data.get("company")
        with transaction.atomic():
            if company:
                Company.objects.select_for_update().get(pk=company.pk)
            if not is_platform_user(request.user):
                has_pro = visible_devices(request.user).filter(company=company, plan__in=["pro", "vip", "premium", "professional"], is_active=True).exists()
                rule = account_rule(company)
                telegram = form.cleaned_data["source_type"] == "telegram"
                existing = ExternalDataSource.objects.filter(company=company).exclude(pk=pk)
                existing = existing.filter(source_type="telegram") if telegram else existing.exclude(source_type="telegram")
                if not has_pro or not rule.can_add_sources:
                    form.add_error(None, "افزودن منابع سفارشی به پلن VIP نیاز دارد.")
                elif existing.count() >= (rule.max_telegram_sources if telegram else rule.max_sources):
                    form.add_error(None, "سهمیه منابع این حساب تکمیل است.")
                if form.cleaned_data["refresh_interval_seconds"] < rule.min_refresh_seconds:
                    form.add_error("refresh_interval_seconds", f"حداقل فاصله مجاز {rule.min_refresh_seconds} ثانیه است.")
            if not is_platform_user(request.user) and telegram:
                bots = Integration.objects.filter(company=company, kind="telegram", is_active=True)
                if source.credential_reference:
                    bots = bots.filter(key=source.credential_reference)
                if bots.count() != 1:
                    form.add_error(None, "مدیر باید یک اتصال ربات تلگرام فعال برای این حساب تعیین کند.")
                else:
                    form.instance.credential_reference = bots.first().key
            if not form.errors:
                obj = form.save(commit=False)
                if not obj.pk:
                    obj.created_by = request.user
                obj.save()
                audit(request, "source.save", obj)
                return redirect("panel-data-source-list")
    return form_page(request, form, "ویرایش منبع" if pk else "افزودن منبع", "panel-data-source-list", source=source if pk else None, note="JSON: مسیر مانند data.price؛ سایت: انتخابگر CSS مانند .price؛ تلگرام: شناسه کانال و الگوی اختیاری مانند قیمت: (\\d+).")


def data_source_create(request):
    return source_editor(request)


def data_source_edit(request, pk):
    return source_editor(request, pk)


@login_required
@require_POST
def source_refresh(request, pk):
    source = get_object_or_404(visible_sources(request.user), pk=pk)
    if not is_platform_user(request.user) and source.company_id not in managed_company_ids(request.user) and source.created_by_id != request.user.pk:
        raise PermissionDenied
    if source.last_attempt_at and (timezone.now()-source.last_attempt_at).total_seconds() < source.refresh_interval_seconds:
        messages.info(request, "برای دریافت بعدی تا پایان فاصله تنظیم‌شده صبر کنید.")
    else:
        messages.success(request, "داده دریافت شد." if refresh_source(source) else "داده دریافت نشد؛ آدرس، دسترسی و قالب پاسخ را بررسی کنید.")
    return redirect("panel-data-source-list")


@owner_only
def company_list(request):
    rows = [{"cells": [c.name, c.get_account_kind_display(), str(c.parent or "—"), c.devices.count(), c.memberships.count(), "فعال" if c.is_active else "غیرفعال"], "url": reverse("panel-company-edit", args=[c.pk])} for c in Company.objects.select_related("parent").prefetch_related("devices", "memberships")]
    return list_page(request, "حساب‌ها، شرکت‌ها و زیرمجموعه‌ها", ["نام", "نوع", "شرکت مادر", "گجت‌ها", "کاربران", "وضعیت"], rows, reverse("panel-company-create"))


@owner_only
def company_editor(request, pk=None):
    company = get_object_or_404(Company, pk=pk) if pk else None
    form = CompanyEditForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit(request, "company.save", obj)
        return redirect("panel-company-list")
    return form_page(request, form, "مدیریت حساب / شرکت", "panel-company-list")


def company_create(request):
    return company_editor(request)


@owner_only
def user_list(request):
    users = get_user_model().objects.prefetch_related("company_memberships__company", "assigned_devices")
    query = request.GET.get("q", "")[:100]
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(email__icontains=query))
    rows = [{"cells": [u.get_full_name() or u.username, u.username, " / ".join(str(m.company or m.get_role_display()) for m in u.company_memberships.all()), u.assigned_devices.count(), "فعال" if u.is_active else "غیرفعال"], "url": reverse("panel-user-edit", args=[u.pk])} for u in users]
    return list_page(request, "کاربران و دسترسی‌ها", ["نام", "نام کاربری", "حساب / نقش", "گجت‌ها", "وضعیت"], rows, reverse("panel-user-create"))


@owner_only
def user_editor(request, pk=None):
    user = get_object_or_404(get_user_model(), pk=pk) if pk else None
    form = UserEditForm(request.POST or None, instance=user)
    if not pk:
        form.fields["password"].required = True
    if request.method == "POST" and form.is_valid():
        if user and user.pk == request.user.pk and not form.cleaned_data["is_active"]:
            form.add_error("is_active", "حساب مدیر جاری را نمی‌توان غیرفعال کرد.")
        else:
            user = form.save()
            audit(request, "user.save", user)
            messages.success(request, "کاربر ذخیره شد. نقش و عضویت او را از بخش عضویت‌ها تعیین کنید.")
            return redirect("panel-user-list")
    return form_page(request, form, "مدیریت کاربر", "panel-user-list", managed_user=user)


def user_create(request):
    return user_editor(request)


@login_required
def message_list(request):
    qs = MessageCampaign.objects.all() if is_platform_user(request.user) else MessageCampaign.objects.filter(company_id__in=managed_company_ids(request.user))
    rows = [{"cells": [c.name, str(c.company), c.get_status_display(), c.scheduled_at or "—", c.expires_at or "—", c.last_error or "—"], "url": reverse("panel-message-edit", args=[c.pk])} for c in qs.select_related("company")]
    return list_page(request, "پیام و ارسال لیست قیمت", ["عنوان", "شرکت", "وضعیت", "زمان ارسال", "انقضا", "نتیجه"], rows, reverse("panel-message-create"))


@login_required
def campaign_editor(request, pk=None):
    qs = MessageCampaign.objects.all() if is_platform_user(request.user) else MessageCampaign.objects.filter(company_id__in=managed_company_ids(request.user))
    campaign = get_object_or_404(qs, pk=pk) if pk else None
    if campaign:
        manage_company(request, campaign.company)
        if campaign.status == "sent":
            raise PermissionDenied("پیام ارسال‌شده قابل ویرایش نیست؛ پیام جدید بسازید.")
    form = CampaignForm(request.POST or None, instance=campaign)
    form.fields["company"].queryset = visible_companies(request.user).filter(pk__in=managed_company_ids(request.user))
    form.fields["target_devices"].queryset = visible_devices(request.user)
    form.fields["price_list"].queryset = PriceList.objects.filter(company__in=form.fields["company"].queryset)
    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data["company"]
        manage_company(request, company)
        targets = form.cleaned_data["target_devices"]
        prices = form.cleaned_data.get("price_list")
        if targets.exclude(company_id__in=company_tree_ids(company.pk)).exists() or (prices and prices.company_id != company.pk):
            form.add_error(None, "تمام مقاصد و لیست قیمت باید متعلق به همان شرکت باشند.")
        elif not is_platform_user(request.user) and any(not rule_for(d.normalized_plan).can_send_messages for d in targets):
            form.add_error("target_devices", "ارسال سازمانی فقط برای گجت‌های Pro مجاز است.")
        else:
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.status = "scheduled"
                obj.created_by = request.user
                obj.save()
                form.save_m2m()
                audit(request, "campaign.schedule", obj)
            messages.success(request, "پیام در صف ارسال قرار گرفت.")
            return redirect("panel-message-list")
    return form_page(request, form, "ارسال پیام یا لیست قیمت", "panel-message-list", note="زمان‌ها مطابق منطقه زمانی تنظیم‌شده در سامانه‌اند. دستگاه پیام منقضی را نمایش نمی‌دهد.")


def message_create(request):
    return campaign_editor(request)


def message_edit(request, pk):
    return campaign_editor(request, pk)


@login_required
def price_lists(request):
    qs = PriceList.objects.all() if is_platform_user(request.user) else PriceList.objects.filter(Q(company_id__in=managed_company_ids(request.user)) | Q(target_devices__in=visible_devices(request.user))).distinct()
    rows = [{"cells": [p.name, str(p.company), p.revision, p.items.count(), p.updated_at], "url": reverse("panel-price-detail", args=[p.pk])} for p in qs.select_related("company").prefetch_related("items")]
    return list_page(request, "لیست قیمت شرکت‌ها", ["لیست", "شرکت", "نسخه", "اقلام", "بروزرسانی"], rows, reverse("panel-price-create") if is_platform_user(request.user) or managed_company_ids(request.user) else None)


@login_required
def price_editor(request, pk=None):
    qs = PriceList.objects.all() if is_platform_user(request.user) else PriceList.objects.filter(company_id__in=managed_company_ids(request.user))
    price_list = get_object_or_404(qs, pk=pk) if pk else None
    form = PriceListForm(request.POST or None, instance=price_list)
    form.fields["company"].queryset = Company.objects.filter(pk__in=managed_company_ids(request.user))
    form.fields["target_devices"].queryset = visible_devices(request.user)
    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data["company"]
        manage_company(request, company)
        if form.cleaned_data["target_devices"].exclude(company_id__in=company_tree_ids(company.pk)).exists():
            form.add_error("target_devices", "مقاصد باید متعلق به شرکت انتخابی باشند.")
        else:
            obj = form.save()
            audit(request, "price_list.save", obj)
            return redirect("panel-price-detail", pk=obj.pk)
    return form_page(request, form, "مدیریت لیست قیمت", "panel-price-list")


@login_required
def price_detail(request, pk):
    qs = PriceList.objects.all() if is_platform_user(request.user) else PriceList.objects.filter(Q(company_id__in=managed_company_ids(request.user)) | Q(target_devices__in=visible_devices(request.user))).distinct()
    price_list = get_object_or_404(qs, pk=pk)
    purge_expired_content()
    editable = is_platform_user(request.user) or (price_list.company_id in managed_company_ids(request.user) and account_rule(price_list.company).can_send_messages)
    return render(request, "core/portal/prices.html", {"price_list": price_list, "editable": editable})


@login_required
def price_item_editor(request, pk, item_pk=None):
    price_list = get_object_or_404(PriceList.objects.filter(company_id__in=managed_company_ids(request.user)), pk=pk)
    manage_company(request, price_list.company)
    item = get_object_or_404(price_list.items, pk=item_pk) if item_pk else PriceItem(price_list=price_list)
    form = PriceItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = PriceList.objects.select_for_update().get(pk=pk)
            form.save()
            locked.revision += 1
            locked.save()
            audit(request, "price_item.save", item)
        return redirect("panel-price-detail", pk=pk)
    return form_page(request, form, "قیمت کالا / خدمت", "panel-price-list")


@owner_only
def integrations(request):
    rows = [{"cells": [i.name, i.key, i.get_kind_display(), "تنظیم شده" if i.encrypted_secret else "بدون توکن", "فعال" if i.is_active else "غیرفعال"], "url": reverse("panel-integration-edit", args=[i.pk])} for i in Integration.objects.all()]
    return list_page(request, "اتصال‌ها و اعتبارنامه‌ها", ["نام", "شناسه", "نوع", "اعتبارنامه", "وضعیت"], rows, reverse("panel-integration-create"), "مقادیر محرمانه رمزگذاری می‌شوند و پس از ذخیره در فرم نمایش داده نمی‌شوند.")


@owner_only
def integration_editor(request, pk=None):
    obj = get_object_or_404(Integration, pk=pk) if pk else None
    form = IntegrationForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit(request, "integration.save", obj)
        return redirect("panel-integrations")
    return form_page(request, form, "تنظیم اتصال", "panel-integrations", note="شناسه‌های سیستمی: wordpress، wordpress-sync، mqtt، metrics، notifications، monitor. هر ربات تلگرام شناسه جداگانه دارد.")


@owner_only
def settings_editor(request):
    form = SettingsForm(request.POST or None, instance=platform_settings())
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "settings.save", "سامانه")
        messages.success(request, "تنظیمات ذخیره شد.")
        return redirect("panel-settings")
    return form_page(request, form, "تنظیمات سامانه", note="آدرس عمومی برای لینک‌های دستگاه و ربات استفاده می‌شود. DNS و گواهی HTTPS باید در میزبان دامنه فعال باشند.")


@owner_only
def rules(request):
    for plan in ["simple", "pro"]:
        if not PlanRule.objects.filter(plan_name=plan).exists():
            rule_for(plan).save()
    rows = [{"cells": ["VIP / Pro" if p.plan_name == "pro" else "ساده", p.max_sources, p.max_telegram_sources, p.min_refresh_seconds, "بله" if p.can_send_messages else "خیر"], "url": reverse("panel-rule-edit", args=[p.pk])} for p in PlanRule.objects.all()]
    return list_page(request, "پلن‌ها و سهمیه‌ها", ["پلن", "منابع سفارشی", "تلگرام", "فاصله دریافت", "ارسال پیام"], rows)


@owner_only
def rule_editor(request, pk):
    rule = get_object_or_404(PlanRule, pk=pk)
    form = RuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        form.save()
        from core.config_sync import refresh_all_device_configs
        refresh_all_device_configs()
        audit(request, "plan.save", rule)
        return redirect("panel-rules")
    return form_page(request, form, "سهمیه‌ها و امکانات " + rule.plan_name, "panel-rules")


@owner_only
def templates(request):
    rows = [{"cells": [t.name, t.plan_type, t.version, t.pages.count(), "فعال" if t.is_active else "غیرفعال"], "url": reverse("panel-template-detail", args=[t.pk])} for t in UITemplate.objects.prefetch_related("pages")]
    return list_page(request, "تم‌ها و صفحات", ["قالب", "پلن", "نسخه", "صفحات", "وضعیت"], rows, reverse("panel-template-create"))


@owner_only
def template_editor(request, pk=None):
    obj = get_object_or_404(UITemplate, pk=pk) if pk else None
    form = TemplateForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            if obj.is_active:
                UITemplate.objects.filter(plan_type=obj.plan_type, is_active=True).exclude(pk=obj.pk).update(is_active=False)
            from core.config_sync import refresh_all_device_configs
            refresh_all_device_configs()
        audit(request, "template.save", obj)
        return redirect("panel-template-detail", pk=obj.pk)
    return form_page(request, form, "رنگ و قالب نمایش", "panel-templates")


@owner_only
def template_detail(request, pk):
    template = get_object_or_404(UITemplate.objects.prefetch_related("pages__elements"), pk=pk)
    return render(request, "core/portal/templates.html", {"template": template})


@owner_only
def page_editor(request, pk, page_pk=None):
    template = get_object_or_404(UITemplate, pk=pk)
    page = get_object_or_404(template.pages, pk=page_pk) if page_pk else UIPage(template=template)
    form = PageForm(request.POST or None, instance=page)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "page.save", page)
        return redirect("panel-template-detail", pk=pk)
    return form_page(request, form, "تنظیم صفحه", "panel-templates")


@owner_only
def element_editor(request, pk, element_pk=None):
    page = get_object_or_404(UIPage, pk=pk)
    element = get_object_or_404(page.elements, pk=element_pk) if element_pk else UIElement(page=page)
    form = ElementForm(request.POST or None, instance=element)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "element.save", element)
        return redirect("panel-template-detail", pk=page.template_id)
    return form_page(request, form, "عنصر صفحه و اتصال به منبع", "panel-templates")


def service_cards():
    records = {s.service_name: s for s in ServiceHealth.objects.all()}
    resources = {r.service: r for r in ResourceSnapshot.objects.all()}
    result = []
    service_names = [("api", "API"), ("db", "PostgreSQL"), ("redis", "Redis"), ("mqtt", "MQTT"), ("worker", "Worker"), ("beat", "Scheduler"), ("wordpress", "WordPress"), ("telegram", "Telegram")]
    known = {key for key, _ in service_names}
    service_names.extend((key, key) for key in sorted((records.keys() | resources.keys()) - known))
    for key, name in service_names:
        record = records.get(key)
        fresh = record and record.last_check_at > timezone.now() - timedelta(seconds=180)
        resource = resources.get(key)
        if resource and resource.sampled_at < timezone.now() - timedelta(seconds=180):
            resource = None
        result.append({"name": name, "state": record.status if fresh else "unknown", "latency": record.response_time_ms if fresh else None, "resource": resource, "checked": record.last_check_at if record else None})
    return result


@owner_only
def monitoring(request):
    return render(request, "core/portal/monitoring.html", {"services": service_cards(), "sources": ExternalDataSource.objects.all(), "events": AuditEvent.objects.select_related("actor")[:30]})


@owner_only
@require_POST
def check_services_now(request):
    from core.monitoring import check_services
    check_services()
    messages.success(request, "بررسی سرویس‌ها اجرا شد.")
    return redirect("panel-monitoring")


def setup(request):
    from core.secrets import setup_code
    config = platform_settings()
    if config.setup_complete or get_user_model().objects.filter(is_superuser=True).exists():
        return redirect("panel-dashboard")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.core.cache import cache
        key = "setup-attempt:" + request.META.get("REMOTE_ADDR", "unknown")
        attempts = cache.get(key, 0)
        if attempts >= 10:
            return HttpResponse("تلاش بیش از حد؛ ده دقیقه بعد امتحان کنید.", status=429)
        cache.set(key, attempts+1, 600)
        if not secrets.compare_digest(form.cleaned_data["code"], setup_code()):
            form.add_error("code", "کد راه‌اندازی صحیح نیست.")
        elif get_user_model().objects.filter(username=form.cleaned_data["username"]).exists():
            form.add_error("username", "این نام کاربری وجود دارد.")
        else:
            with transaction.atomic():
                config = PlatformSettings.objects.select_for_update().get(pk=1)
                if config.setup_complete:
                    return redirect("panel-dashboard")
                user = get_user_model().objects.create_superuser(username=form.cleaned_data["username"], password=form.cleaned_data["password"])
                config.setup_complete = True
                config.public_base_url = form.cleaned_data["public_base_url"].rstrip("/")
                config.save()
                for plan in ["simple", "pro"]:
                    if not PlanRule.objects.filter(plan_name=plan).exists():
                        rule_for(plan).save()
            login(request, user)
            return redirect("panel-settings")
    return render(request, "core/portal/setup.html", {"form": form})


@login_required
@require_POST
def device_bulk(request):
    ids = request.POST.getlist("devices")
    if not ids or len(ids) > 200 or any(not value.isdigit() for value in ids):
        return HttpResponse("انتخاب دستگاه نامعتبر است.", status=400)
    devices = list(visible_devices(request.user).filter(pk__in=ids))
    if len(devices) != len(set(ids)):
        raise PermissionDenied
    operation = request.POST.get("operation")
    if operation not in {"enable", "disable", "navy", "light", "carbon"}:
        return HttpResponse("عملیات نامعتبر است.", status=400)
    for device in devices:
        if not is_platform_owner(request.user) and (device.company_id not in managed_company_ids(request.user) or device.normalized_plan != "pro"):
            raise PermissionDenied
        if operation in {"navy", "light", "carbon"} and not is_platform_owner(request.user) and not rule_for(device.normalized_plan).can_change_theme:
            raise PermissionDenied
        if operation == "enable" and (not device.is_active or device.provisioning_state == "suspended"):
            raise PermissionDenied("دستگاه تعلیق‌شده فقط توسط مدیر اصلی آزاد می‌شود.")
    with transaction.atomic():
        for device in devices:
            if operation in {"enable", "disable"}:
                device.customer_enabled = operation == "enable"
                device.save(update_fields=["customer_enabled", "updated_at"])
            else:
                DevicePreference.objects.update_or_create(device=device, defaults={"theme": operation})
            audit(request, "device.bulk." + operation, device)
    messages.success(request, f"تغییرات برای {len(devices)} گجت ذخیره شد.")
    return redirect("panel-device-list")


@owner_only
def membership_editor(request, pk):
    from core.forms import MembershipForm
    from core.models import CompanyMembership
    membership = get_object_or_404(CompanyMembership, pk=pk)
    form = MembershipForm(request.POST or None, instance=membership)
    if request.method == "POST" and form.is_valid():
        if membership.user_id == request.user.pk and not request.user.is_superuser:
            form.add_error(None, "عضویت مدیر جاری را از حساب مدیر دیگری تغییر دهید.")
        else:
            obj = form.save()
            audit(request, "membership.save", obj)
            return redirect("panel-membership-list")
    return form_page(request, form, "ویرایش نقش و عضویت", "panel-membership-list")
