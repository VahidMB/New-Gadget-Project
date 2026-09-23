from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.access import is_platform_owner, is_platform_user, scope_by_company, visible_companies
from core.device_auth import generate_device_token
from core.forms import (
    CompanyForm,
    DeviceForm,
    ExternalDataSourceForm,
    FirmwareUploadForm,
    MembershipForm,
    MessageCampaignForm,
    PortalUserForm,
)
from core.models import Company, CompanyMembership, ExternalDataSource, FirmwareRelease, MessageCampaign, WordPressDevice


def _require_platform_owner(request):
    if not is_platform_owner(request.user):
        raise PermissionDenied("Only platform owners can access this control.")


def _companies_for_request(request):
    companies = visible_companies(request.user)
    if not companies.exists() and not is_platform_user(request.user):
        raise PermissionDenied("This account has no active company membership.")
    return companies


def _add_company_field(form, companies):
    if companies.count() > 1:
        form.fields["company"] = form._meta.model._meta.get_field("company").formfield(queryset=companies)


def _scope_target_devices(form, request):
    if "target_devices" in form.fields:
        form.fields["target_devices"].queryset = scope_by_company(request.user, WordPressDevice.objects.all())


def _selected_company(request, companies):
    slug = request.GET.get("company") or request.POST.get("company")
    if slug:
        return companies.filter(slug=slug).first()
    return companies.first()


@login_required
def dashboard(request):
    companies = _companies_for_request(request)
    devices = scope_by_company(request.user, WordPressDevice.objects.all())
    campaigns = scope_by_company(request.user, MessageCampaign.objects.all())
    sources = scope_by_company(request.user, ExternalDataSource.objects.all())
    return render(
        request,
        "core/portal/dashboard.html",
        {
            "device_count": devices.count(),
            "campaign_count": campaigns.count(),
            "source_count": sources.count(),
            "companies": companies,
            "is_platform_user": is_platform_user(request.user),
            "is_platform_owner": is_platform_owner(request.user),
        },
    )


@login_required
def device_list(request):
    devices = scope_by_company(request.user, WordPressDevice.objects.select_related("company")).order_by("company__name", "name", "external_id")
    _companies_for_request(request)
    return render(request, "core/portal/device_list.html", {"devices": devices, "is_platform_user": is_platform_user(request.user), "is_platform_owner": is_platform_owner(request.user)})


@login_required
def device_detail(request, pk):
    _companies_for_request(request)
    device = get_object_or_404(
        scope_by_company(request.user, WordPressDevice.objects.select_related("company", "status").prefetch_related("firmware_deployments__release")),
        pk=pk,
    )
    return render(request, "core/portal/device_detail.html", {"device": device, "is_platform_user": is_platform_user(request.user), "is_platform_owner": is_platform_owner(request.user)})


@login_required
def device_create(request):
    _require_platform_owner(request)
    if request.method == "POST":
        form = DeviceForm(request.POST)
        if form.is_valid():
            device = form.save(commit=False)
            device.save()
            messages.success(request, "دستگاه ایجاد شد.")
            return redirect("panel-device-detail", pk=device.pk)
    else:
        form = DeviceForm()
    return render(request, "core/portal/device_form.html", {"form": form, "heading": "افزودن دستگاه", "is_platform_user": True, "is_platform_owner": True})


@login_required
def device_edit(request, pk):
    _companies_for_request(request)
    device = get_object_or_404(scope_by_company(request.user, WordPressDevice.objects.all()), pk=pk)
    if request.method == "POST":
        form = DeviceForm(request.POST, instance=device)
        if not is_platform_user(request.user):
            for field_name in ("company", "external_id", "customer_external_id", "serial_number", "hardware_model", "plan"):
                form.fields.pop(field_name)
        if form.is_valid():
            form.save()
            messages.success(request, "تغییرات دستگاه ذخیره شد.")
            return redirect("panel-device-detail", pk=device.pk)
    else:
        form = DeviceForm(instance=device)
        if not is_platform_user(request.user):
            for field_name in ("company", "external_id", "customer_external_id", "serial_number", "hardware_model", "plan"):
                form.fields.pop(field_name)
    return render(request, "core/portal/device_form.html", {"form": form, "heading": "ویرایش دستگاه", "device": device, "is_platform_user": is_platform_user(request.user), "is_platform_owner": is_platform_owner(request.user)})


@login_required
def device_token_rotate(request, pk):
    _require_platform_owner(request)
    if request.method != "POST":
        raise PermissionDenied("Provisioning requires a form submission.")
    device = get_object_or_404(WordPressDevice, pk=pk)
    token, token_hash = generate_device_token()
    device.device_token_hash = token_hash
    device.device_token_created_at = timezone.now()
    device.provisioning_state = WordPressDevice.ProvisioningState.PROVISIONED
    device.is_active = True
    device.save(update_fields=["device_token_hash", "device_token_created_at", "provisioning_state", "is_active", "updated_at"])
    request.session["portal_device_token"] = {"device_id": device.pk, "token": token}
    return redirect("panel-device-token-success", pk=device.pk)


@login_required
def device_token_success(request, pk):
    _require_platform_owner(request)
    payload = request.session.pop("portal_device_token", None)
    if not payload or payload.get("device_id") != pk:
        return redirect("panel-device-detail", pk=pk)
    device = get_object_or_404(WordPressDevice, pk=pk)
    return render(request, "core/portal/device_token_success.html", {"device": device, "token": payload["token"], "is_platform_user": True, "is_platform_owner": True})


@login_required
def device_activation_toggle(request, pk):
    _require_platform_owner(request)
    if request.method != "POST":
        raise PermissionDenied("Activation requires a form submission.")
    device = get_object_or_404(WordPressDevice, pk=pk)
    device.is_active = not device.is_active
    device.provisioning_state = WordPressDevice.ProvisioningState.SUSPENDED if not device.is_active else WordPressDevice.ProvisioningState.PROVISIONED
    device.save(update_fields=["is_active", "provisioning_state", "updated_at"])
    return redirect("panel-device-detail", pk=device.pk)


@login_required
def message_list(request):
    _companies_for_request(request)
    campaigns = scope_by_company(request.user, MessageCampaign.objects.select_related("company", "created_by"))
    return render(request, "core/portal/message_list.html", {"campaigns": campaigns})


@login_required
def message_create(request):
    companies = _companies_for_request(request)
    selected_company = _selected_company(request, companies)
    if request.method == "POST":
        form = MessageCampaignForm(request.POST)
        _add_company_field(form, companies)
        _scope_target_devices(form, request)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.company = form.cleaned_data.get("company") or selected_company
            if campaign.company is None:
                form.add_error(None, "Choose a company.")
            elif not form.cleaned_data["target_devices"]:
                form.add_error("target_devices", "Choose at least one target device.")
            elif form.cleaned_data["target_devices"].exclude(company=campaign.company).exists():
                form.add_error("target_devices", "All selected devices must belong to the selected company.")
            else:
                campaign.created_by = request.user
                campaign.save()
                form.save_m2m()
                return redirect("panel-message-list")
    else:
        form = MessageCampaignForm()
        _add_company_field(form, companies)
        _scope_target_devices(form, request)
    return render(request, "core/portal/message_form.html", {"form": form, "companies": companies})


@login_required
def message_edit(request, pk):
    companies = _companies_for_request(request)
    campaign = get_object_or_404(scope_by_company(request.user, MessageCampaign.objects.all()), pk=pk)
    if request.method == "POST":
        form = MessageCampaignForm(request.POST, instance=campaign)
        _add_company_field(form, companies)
        _scope_target_devices(form, request)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.company = form.cleaned_data.get("company") or campaign.company
            if form.cleaned_data["target_devices"].exclude(company=updated.company).exists():
                form.add_error("target_devices", "همهٔ دستگاه‌های انتخاب‌شده باید متعلق به همان شرکت باشند.")
            else:
                updated.save()
                form.save_m2m()
                return redirect("panel-message-list")
    else:
        form = MessageCampaignForm(instance=campaign)
        _add_company_field(form, companies)
        _scope_target_devices(form, request)
    return render(request, "core/portal/message_form.html", {"form": form, "companies": companies, "heading": "ویرایش پیام"})


@login_required
def data_source_list(request):
    _companies_for_request(request)
    sources = scope_by_company(request.user, ExternalDataSource.objects.select_related("company"))
    return render(request, "core/portal/data_source_list.html", {"sources": sources})


@login_required
def data_source_create(request):
    companies = _companies_for_request(request)
    selected_company = _selected_company(request, companies)
    if request.method == "POST":
        form = ExternalDataSourceForm(request.POST)
        _add_company_field(form, companies)
        if form.is_valid():
            source = form.save(commit=False)
            source.company = form.cleaned_data.get("company") or selected_company
            if source.company is None:
                form.add_error(None, "Choose a company.")
            else:
                source.save()
                return redirect("panel-data-source-list")
    else:
        form = ExternalDataSourceForm()
        _add_company_field(form, companies)
    return render(request, "core/portal/data_source_form.html", {"form": form, "companies": companies})


@login_required
def data_source_edit(request, pk):
    companies = _companies_for_request(request)
    source = get_object_or_404(scope_by_company(request.user, ExternalDataSource.objects.all()), pk=pk)
    if request.method == "POST":
        form = ExternalDataSourceForm(request.POST, instance=source)
        _add_company_field(form, companies)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.company = form.cleaned_data.get("company") or source.company
            updated.save()
            return redirect("panel-data-source-list")
    else:
        form = ExternalDataSourceForm(instance=source)
        _add_company_field(form, companies)
    return render(request, "core/portal/data_source_form.html", {"form": form, "companies": companies, "heading": "ویرایش منبع داده"})


@login_required
def company_list(request):
    _require_platform_owner(request)
    return render(request, "core/portal/company_list.html", {"companies": Company.objects.all(), "is_platform_user": True, "is_platform_owner": True})


@login_required
def company_create(request):
    _require_platform_owner(request)
    form = CompanyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("panel-company-list")
    return render(request, "core/portal/generic_form.html", {"form": form, "heading": "افزودن شرکت", "cancel_url": "panel-company-list", "is_platform_user": True, "is_platform_owner": True})


@login_required
def user_list(request):
    _require_platform_owner(request)
    users = get_user_model().objects.prefetch_related("company_memberships__company").order_by("username")
    return render(request, "core/portal/user_list.html", {"users": users, "is_platform_user": True, "is_platform_owner": True})


@login_required
def user_create(request):
    _require_platform_owner(request)
    form = PortalUserForm(request.POST or None, companies=Company.objects.filter(is_active=True))
    if request.method == "POST" and form.is_valid():
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=form.cleaned_data["username"], password=form.cleaned_data["password"],
            first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"], email=form.cleaned_data["email"],
        )
        CompanyMembership.objects.create(user=user, company=form.cleaned_data["company"], role=form.cleaned_data["role"])
        return redirect("panel-user-list")
    return render(request, "core/portal/generic_form.html", {"form": form, "heading": "افزودن کاربر و نقش", "cancel_url": "panel-user-list", "is_platform_user": True, "is_platform_owner": True})


@login_required
def membership_list(request):
    _require_platform_owner(request)
    memberships = CompanyMembership.objects.select_related("user", "company")
    return render(request, "core/portal/membership_list.html", {"memberships": memberships, "is_platform_user": True, "is_platform_owner": True})


@login_required
def membership_create(request):
    _require_platform_owner(request)
    form = MembershipForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("panel-membership-list")
    return render(request, "core/portal/generic_form.html", {"form": form, "heading": "افزودن عضویت", "cancel_url": "panel-membership-list", "is_platform_user": True, "is_platform_owner": True})


@login_required
def firmware_list(request):
    if not is_platform_user(request.user):
        raise PermissionDenied("Only platform users can manage firmware.")
    releases = FirmwareRelease.objects.all()
    return render(request, "core/portal/firmware_list.html", {"releases": releases})


@login_required
def firmware_upload(request):
    if not is_platform_user(request.user):
        raise PermissionDenied("Only platform users can upload firmware.")
    if request.method == "POST":
        form = FirmwareUploadForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("panel-firmware-list")
    else:
        form = FirmwareUploadForm()
    return render(request, "core/portal/firmware_form.html", {"form": form})
