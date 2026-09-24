from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import regex
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import (Company, CompanyMembership, WordPressDevice, ExternalDataSource, DevicePreference, Integration, PlatformSettings, PlanRule, UITemplate, UIPage, UIElement, PriceList, PriceItem, MessageCampaign)


class PersianModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "name": "نام", "company": "حساب / شرکت مالک", "parent": "شرکت مادر", "slug": "شناسه کوتاه",
            "is_active": "فعال", "account_kind": "نوع حساب", "contact_name": "نام مسئول", "contact_phone": "شماره تماس",
            "external_id": "شناسه گجت", "assigned_user": "کاربر اختصاص‌یافته", "recipient_name": "نام استفاده‌کننده / نماینده",
            "recipient_contact": "اطلاعات تماس", "group_name": "گروه دستگاه", "customer_enabled": "فعال برای مشتری",
            "hardware_model": "مدل سخت‌افزار", "serial_number": "شماره سریال", "plan": "پلن", "provisioning_state": "وضعیت راه‌اندازی",
            "source_type": "نوع منبع", "category": "دسته اطلاعات", "display_key": "کلید نمایش", "endpoint_url": "آدرس منبع",
            "value_path": "مسیر مقدار JSON / انتخابگر CSS / فیلد RSS", "title_path": "مسیر عنوان JSON", "unit": "واحد (تومان، دلار، گرم و …)",
            "ttl_seconds": "اعتبار داده (ثانیه)", "refresh_interval_seconds": "فاصله دریافت داده (ثانیه)", "extraction_pattern": "الگوی استخراج متن (گروه اول)",
            "telegram_chat_id": "شناسه کانال / گروه تلگرام", "credential_reference": "شناسه اتصال احراز هویت",
            "theme": "تم", "rotation_seconds": "زمان تعویض محتوا (ثانیه)", "live_updates": "به‌روزرسانی زنده", "custom_primary": "رنگ اختصاصی",
            "key": "شناسه اتصال", "kind": "نوع اتصال", "endpoint": "آدرس / میزبان", "username": "نام کاربری", "port": "پورت", "use_tls": "اتصال رمزگذاری‌شده", "options": "گزینه‌های تکمیلی JSON",
            "site_name": "نام سامانه", "public_base_url": "آدرس عمومی سامانه", "timezone": "منطقه زمانی", "heartbeat_timeout": "مهلت قطع ارتباط (ثانیه)", "audit_retention_days": "نگهداری سوابق مدیریت (روز)", "test_mode": "حالت آزمایشی",
            "plan_name": "پلن", "can_customize_ui": "شخصی‌سازی ظاهر", "can_change_theme": "انتخاب تم", "can_add_pages": "صفحات سفارشی", "can_add_sources": "منابع سفارشی", "can_send_messages": "ارسال پیام سازمانی",
            "max_pages": "حداکثر صفحات", "max_elements_per_page": "حداکثر عناصر هر صفحه", "max_sources": "سقف منابع سفارشی", "max_telegram_sources": "سقف کانال و گروه تلگرام", "min_refresh_seconds": "حداقل فاصله دریافت (ثانیه)",
            "plan_type": "پلن قالب", "version": "نسخه", "default_theme": "رنگ‌های قالب JSON", "default_screen": "مشخصات نمایش JSON", "default_rules": "قواعد قالب JSON",
            "page_key": "شناسه صفحه", "page_type": "نوع صفحه", "priority": "ترتیب", "refresh_interval_ms": "فاصله نمایش (میلی‌ثانیه)", "visible_when": "شرایط نمایش JSON",
            "element_type": "نوع عنصر", "label": "عنوان", "source_key": "کلید منبع", "width": "عرض", "height": "ارتفاع", "font_size": "اندازه قلم", "color": "رنگ", "style": "سبک JSON", "z_index": "لایه", "is_visible": "قابل نمایش", "config": "گزینه‌های عنصر JSON",
            "target_devices": "دستگاه‌های مقصد", "code": "کد کالا", "amount": "قیمت", "valid_until": "معتبر تا", "message": "متن پیام", "scheduled_at": "زمان ارسال", "expires_at": "زمان انقضا", "price_list": "لیست قیمت همراه",
            "role": "نقش", "user": "کاربر", "email": "ایمیل", "first_name": "نام", "last_name": "نام خانوادگی",
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            if isinstance(field, forms.DateTimeField):
                field.widget = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})
            if isinstance(field, forms.JSONField):
                field.widget = forms.Textarea(attrs={"rows": 3, "dir": "ltr"})


class CompanyEditForm(PersianModelForm):
    class Meta:
        model = Company
        fields = ["name", "slug", "account_kind", "parent", "contact_name", "contact_phone", "is_active"]
    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        seen = {self.instance.pk} if self.instance.pk else set()
        cursor = parent
        while cursor:
            if cursor.pk in seen:
                raise ValidationError("رابطه شرکت مادر نمی‌تواند حلقه داشته باشد.")
            seen.add(cursor.pk)
            cursor = cursor.parent
        return parent


class DeviceEditForm(PersianModelForm):
    plan = forms.ChoiceField(choices=[("simple", "ساده"), ("pro", "VIP / Pro")])
    class Meta:
        model = WordPressDevice
        fields = ["company", "external_id", "serial_number", "hardware_model", "name", "plan", "is_active", "assigned_user", "recipient_name", "recipient_contact", "group_name", "customer_enabled"]
    def clean_external_id(self):
        value = self.cleaned_data["external_id"]
        if not regex.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
            raise ValidationError("شناسه فقط شامل حروف لاتین، عدد، نقطه، خط تیره و زیرخط است.")
        if self.instance.pk and value != self.instance.external_id:
            raise ValidationError("شناسه دستگاه ثبت‌شده قابل تغییر نیست.")
        return value
    def clean(self):
        data = super().clean()
        company = data.get("company") or self.instance.company
        user = data.get("assigned_user")
        if user and (not company or not CompanyMembership.objects.filter(user=user, company=company, is_active=True).exists()):
            self.add_error("assigned_user", "کاربر باید عضو همین حساب / شرکت باشد.")
        return data


class SourceForm(PersianModelForm):
    class Meta:
        model = ExternalDataSource
        fields = ["company", "name", "source_type", "category", "display_key", "endpoint_url", "title_path", "value_path", "unit", "refresh_interval_seconds", "ttl_seconds", "extraction_pattern", "telegram_chat_id", "credential_reference", "is_active"]
    def clean(self):
        data = super().clean()
        if data.get("source_type") in {"http", "web", "rss"}:
            url = urlsplit(data.get("endpoint_url", ""))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                self.add_error("endpoint_url", "آدرس عمومی معتبر HTTP/HTTPS لازم است.")
        if data.get("source_type") == "telegram" and not data.get("telegram_chat_id"):
            self.add_error("telegram_chat_id", "شناسه کانال یا گروه مجاز را وارد کنید.")
        for field in ["ttl_seconds", "refresh_interval_seconds"]:
            if not 5 <= data.get(field, 0) <= 86400:
                self.add_error(field, "مقدار باید بین ۵ تا ۸۶۴۰۰ ثانیه باشد.")
        try:
            if data.get("extraction_pattern"):
                regex.compile(data["extraction_pattern"])
        except regex.error:
            self.add_error("extraction_pattern", "الگوی استخراج نامعتبر است.")
        return data


class PreferenceForm(PersianModelForm):
    ordered_sources = forms.CharField(required=False, widget=forms.HiddenInput)
    sources = forms.ModelMultipleChoiceField(queryset=ExternalDataSource.objects.none(), required=False, label="اطلاعات انتخاب‌شده", widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = DevicePreference
        fields = ["theme", "rotation_seconds", "live_updates", "custom_primary"]


class IntegrationForm(PersianModelForm):
    secret = forms.CharField(required=False, label="توکن / گذرواژه جدید", widget=forms.PasswordInput(render_value=False), help_text="خالی بماند: مقدار قبلی حفظ می‌شود.")
    webhook_secret = forms.CharField(required=False, label="کلید Webhook جدید", widget=forms.PasswordInput(render_value=False))
    clear_secret = forms.BooleanField(required=False, label="حذف توکن ذخیره‌شده")
    clear_webhook = forms.BooleanField(required=False, label="حذف کلید Webhook ذخیره‌شده")
    class Meta:
        model = Integration
        fields = ["key", "name", "kind", "company", "endpoint", "username", "port", "use_tls", "options", "is_active"]
    def clean(self):
        data = super().clean()
        reserved = {"mqtt": "mqtt", "wordpress": "wordpress", "wordpress-sync": "wordpress", "metrics": "metrics", "monitor": "monitor", "notifications": "notifications"}
        if data.get("key") in reserved and (data.get("company") or data.get("kind") != reserved[data["key"]]):
            raise ValidationError("این کلید رزرو شده است؛ نوع اتصال باید مطابق کلید و مالک آن عمومی باشد.")
        if self.instance.pk and self.instance.key != data.get("key"):
            raise ValidationError("کلید اتصال موجود قابل تغییر نیست؛ اتصال جدید بسازید.")
        return data
    def clean_options(self):
        options = self.cleaned_data["options"] or {}
        if not isinstance(options, dict):
            raise ValidationError("گزینه‌ها باید یک شیء JSON باشند.")
        if any(any(word in key.lower() for word in ["token", "secret", "password", "authorization"]) for key in options):
            raise ValidationError("مقادیر محرمانه را فقط در فیلد رمزگذاری‌شده وارد کنید.")
        return options
    def save(self, commit=True):
        instance = super().save(commit=False)
        for field, clear, webhook in [("secret", "clear_secret", False), ("webhook_secret", "clear_webhook", True)]:
            if self.cleaned_data.get(field) or self.cleaned_data.get(clear):
                instance.set_secret(self.cleaned_data.get(field, ""), webhook=webhook)
        if commit:
            instance.save()
        return instance


class SettingsForm(PersianModelForm):
    class Meta:
        model = PlatformSettings
        fields = ["site_name", "public_base_url", "timezone", "heartbeat_timeout", "audit_retention_days", "test_mode"]
    def clean_timezone(self):
        value = self.cleaned_data["timezone"]
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValidationError("منطقه زمانی معتبر نیست؛ مثال Asia/Tehran")
        return value
    def clean_public_base_url(self):
        value = self.cleaned_data["public_base_url"].rstrip("/")
        if value and urlsplit(value).path not in {"", "/"}:
            raise ValidationError("آدرس دامنه بدون مسیر داخلی را وارد کنید.")
        return value


class RuleForm(PersianModelForm):
    class Meta:
        model = PlanRule
        fields = ["can_customize_ui", "can_change_theme", "can_add_pages", "can_add_sources", "can_send_messages", "max_pages", "max_elements_per_page", "max_sources", "max_telegram_sources", "min_refresh_seconds", "is_active"]
    def clean_min_refresh_seconds(self):
        value = self.cleaned_data["min_refresh_seconds"]
        if value < 5:
            raise ValidationError("حداقل فاصله دریافت ۵ ثانیه است.")
        return value


class TemplateForm(PersianModelForm):
    primary_color = forms.CharField(label="رنگ اصلی", initial="#3885ff", widget=forms.TextInput(attrs={"type": "color"}))
    background_color = forms.CharField(label="رنگ پس‌زمینه", initial="#233b55", widget=forms.TextInput(attrs={"type": "color"}))
    plan_type = forms.ChoiceField(choices=[("simple", "ساده"), ("pro", "VIP")], label="پلن")
    class Meta:
        model = UITemplate
        fields = ["name", "version", "plan_type", "default_screen", "default_rules", "is_active"]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for key in ["primary_color", "background_color"]:
                self.fields[key].initial = self.instance.default_theme.get(key, self.fields[key].initial)
    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.default_theme = {**obj.default_theme, "primary_color": self.cleaned_data["primary_color"], "background_color": self.cleaned_data["background_color"]}
        if commit:
            obj.save()
        return obj


class PageForm(PersianModelForm):
    page_type = forms.ChoiceField(choices=[("market", "قیمت‌های بازار"), ("price_list", "لیست قیمت شرکت"), ("news", "اخبار"), ("message", "پیام"), ("clock", "ساعت"), ("weather", "آب‌وهوا"), ("custom", "سفارشی")])
    class Meta:
        model = UIPage
        fields = ["page_key", "page_type", "priority", "refresh_interval_ms", "visible_when", "is_active"]


class ElementForm(PersianModelForm):
    element_type = forms.ChoiceField(choices=[("price", "قیمت"), ("text", "متن"), ("clock", "ساعت"), ("image", "تصویر"), ("list", "لیست")])
    class Meta:
        model = UIElement
        fields = ["element_type", "label", "source_key", "x", "y", "width", "height", "font_size", "color", "z_index", "style", "config", "is_visible"]


class PriceListForm(PersianModelForm):
    class Meta:
        model = PriceList
        fields = ["company", "name", "target_devices", "is_active"]


class PriceItemForm(PersianModelForm):
    class Meta:
        model = PriceItem
        fields = ["name", "code", "amount", "unit", "valid_until"]
    def clean_valid_until(self):
        value = self.cleaned_data["valid_until"]
        if value <= timezone.now():
            raise ValidationError("زمان اعتبار باید در آینده باشد.")
        return value


class CampaignForm(PersianModelForm):
    send_now = forms.BooleanField(required=False, label="ارسال فوری")
    class Meta:
        model = MessageCampaign
        fields = ["company", "name", "message", "price_list", "target_devices", "scheduled_at", "expires_at"]
    def clean(self):
        data = super().clean()
        when = timezone.now() if data.get("send_now") else data.get("scheduled_at")
        if not when:
            self.add_error("scheduled_at", "زمان ارسال را مشخص کنید یا ارسال فوری را انتخاب کنید.")
        if not data.get("expires_at") or (when and data["expires_at"] <= when):
            self.add_error("expires_at", "انقضای پیام باید بعد از زمان ارسال باشد.")
        if not data.get("target_devices"):
            self.add_error("target_devices", "حداقل یک دستگاه را انتخاب کنید.")
        data["scheduled_at"] = when
        return data


class UserEditForm(PersianModelForm):
    password = forms.CharField(required=False, label="گذرواژه جدید", widget=forms.PasswordInput)
    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
    def clean_password(self):
        password = self.cleaned_data["password"]
        if password:
            validate_password(password, self.instance)
        return password
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["password"]:
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class SetupForm(forms.Form):
    code = forms.CharField(label="کد یک‌بار مصرف راه‌اندازی", widget=forms.PasswordInput)
    username = forms.CharField(label="نام کاربری مدیر")
    password = forms.CharField(label="گذرواژه مدیر", widget=forms.PasswordInput)
    public_base_url = forms.URLField(label="آدرس سامانه", required=False)
    def clean_password(self):
        value = self.cleaned_data["password"]
        validate_password(value)
        return value
