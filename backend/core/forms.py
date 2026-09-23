from django import forms
from django.contrib.auth import get_user_model
from django.conf import settings

from core.models import Company, CompanyMembership, ExternalDataSource, FirmwareRelease, MessageCampaign, WordPressDevice


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "slug", "is_active")
        labels = {"name": "نام شرکت", "slug": "شناسهٔ کوتاه", "is_active": "شرکت فعال است"}


class MembershipForm(forms.ModelForm):
    class Meta:
        model = CompanyMembership
        fields = ("user", "company", "role", "is_active")

    def clean(self):
        cleaned_data = super().clean()
        membership = CompanyMembership(
            user=cleaned_data.get("user"),
            company=cleaned_data.get("company"),
            role=cleaned_data.get("role"),
        )
        try:
            membership.clean()
        except forms.ValidationError as exc:
            self.add_error(None, exc)
        return cleaned_data


class PortalUserForm(forms.Form):
    username = forms.CharField(max_length=150, label="نام کاربری")
    first_name = forms.CharField(max_length=150, required=False, label="نام")
    last_name = forms.CharField(max_length=150, required=False, label="نام خانوادگی")
    email = forms.EmailField(required=False, label="ایمیل")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="گذرواژه")
    company = forms.ModelChoiceField(queryset=Company.objects.none(), required=False, label="شرکت")
    role = forms.ChoiceField(choices=CompanyMembership.Role.choices, label="نقش")

    def __init__(self, *args, companies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = companies if companies is not None else Company.objects.all()

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("این نام کاربری قبلاً استفاده شده است.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        company = cleaned_data.get("company")
        if role in CompanyMembership.COMPANY_ROLES and not company:
            self.add_error("company", "برای نقش شرکتی، شرکت را انتخاب کنید.")
        if role in CompanyMembership.PLATFORM_ROLES and company:
            self.add_error("company", "نقش‌های پلتفرم نباید به شرکت متصل باشند.")
        return cleaned_data


class DeviceForm(forms.ModelForm):
    class Meta:
        model = WordPressDevice
        fields = (
            "company", "external_id", "customer_external_id", "serial_number", "hardware_model",
            "name", "plan", "is_active",
        )
        labels = {
            "company": "شرکت",
            "external_id": "شناسهٔ دستگاه",
            "customer_external_id": "شناسهٔ مشتری",
            "serial_number": "شماره سریال",
            "hardware_model": "مدل سخت‌افزار",
            "name": "نام نمایشی دستگاه",
            "plan": "نوع اشتراک",
            "is_active": "دستگاه فعال است",
        }


class MessageCampaignForm(forms.ModelForm):
    class Meta:
        model = MessageCampaign
        fields = ("name", "message", "target_devices", "status", "scheduled_at")
        labels = {
            "name": "نام پیام",
            "message": "متن پیام",
            "target_devices": "دستگاه‌های دریافت‌کننده",
            "status": "وضعیت",
            "scheduled_at": "زمان ارسال",
        }
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6}),
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = (
            (MessageCampaign.Status.DRAFT, "پیش‌نویس"),
            (MessageCampaign.Status.SCHEDULED, "زمان‌بندی‌شده"),
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == MessageCampaign.Status.SCHEDULED and not cleaned_data.get("scheduled_at"):
            self.add_error("scheduled_at", "برای پیام زمان‌بندی‌شده، زمان ارسال را وارد کنید.")
        return cleaned_data


class ExternalDataSourceForm(forms.ModelForm):
    class Meta:
        model = ExternalDataSource
        fields = (
            "name",
            "source_type",
            "display_key",
            "endpoint_url",
            "refresh_interval_seconds",
            "credential_reference",
            "title_path",
            "value_path",
            "image_path",
            "is_active",
        )
        labels = {
            "name": "نام منبع",
            "source_type": "نوع منبع",
            "display_key": "کلید نمایش",
            "endpoint_url": "آدرس API یا منبع",
            "refresh_interval_seconds": "بازهٔ بروزرسانی (ثانیه)",
            "credential_reference": "نام credential ذخیره‌شده",
            "title_path": "مسیر عنوان در پاسخ",
            "value_path": "مسیر مقدار در پاسخ",
            "image_path": "مسیر تصویر در پاسخ",
            "is_active": "منبع فعال است",
        }
        widgets = {
            "refresh_interval_seconds": forms.NumberInput(attrs={"min": 60}),
        }


class FirmwareUploadForm(forms.ModelForm):
    class Meta:
        model = FirmwareRelease
        fields = ("hardware_model", "version", "firmware_file", "release_notes", "is_mandatory", "is_active", "published_at")
        labels = {
            "hardware_model": "مدل سخت‌افزار",
            "version": "نسخهٔ Firmware",
            "firmware_file": "فایل Firmware (.bin)",
            "release_notes": "توضیحات نسخه",
            "is_mandatory": "به‌روزرسانی اجباری است",
            "is_active": "نسخه فعال است",
            "published_at": "زمان انتشار",
        }
        widgets = {
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean_firmware_file(self):
        firmware_file = self.cleaned_data["firmware_file"]
        if not firmware_file:
            raise forms.ValidationError("A compiled .bin firmware file is required.")
        if not firmware_file.name.lower().endswith(".bin"):
            raise forms.ValidationError("Only compiled .bin firmware files are accepted.")
        if firmware_file.size > settings.MAX_FIRMWARE_UPLOAD_BYTES:
            raise forms.ValidationError("Firmware file is larger than the permitted upload size.")
        return firmware_file
