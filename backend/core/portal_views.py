from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.access import is_platform_owner, is_platform_user
from core.device_auth import generate_device_token
from core.forms import (
    FirmwareUploadForm,
    MembershipForm,
)
from core.models import CompanyMembership, FirmwareRelease, WordPressDevice


def _require_platform_owner(request):
    if not is_platform_owner(request.user):
        raise PermissionDenied("Only platform owners can access this control.")


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
    return render(request, "core/portal/editor.html", {"form": form, "heading": "افزودن عضویت", "cancel_url": "panel-membership-list", "is_platform_user": True, "is_platform_owner": True})


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
    return render(request, "core/portal/editor.html", {"form": form, "heading": "بارگذاری نسخه نرم‌افزار گجت", "cancel_url": "panel-firmware-list", "note": "خروجی کامپایل‌شده ESP32 با پسوند .bin را انتخاب کنید."})

# The new console replaces legacy routes while preserving public URL names.
from core.console_views import (dashboard, device_list, device_detail, device_create, device_edit, device_activation_toggle, message_list, message_create, message_edit, data_source_list, data_source_create, data_source_edit, company_list, company_create, user_list, user_create)  # noqa: E402,F401
