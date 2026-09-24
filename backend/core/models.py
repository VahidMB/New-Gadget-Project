import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Company(models.Model):
    account_kind = models.CharField(max_length=16, choices=[("personal", "شخصی"), ("business", "شرکت / نمایندگی")], default="business")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="branches")
    contact_name = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name


class CompanyMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Platform owner"
        EMPLOYEE = "employee", "Internal employee"
        COMPANY_ADMIN = "company_admin", "Company admin"
        COMPANY_OPERATOR = "company_operator", "Company operator"
        MEMBER = "member", "کاربر دستگاه"

    PLATFORM_ROLES = {Role.OWNER, Role.EMPLOYEE}
    COMPANY_ROLES = {Role.COMPANY_ADMIN, Role.COMPANY_OPERATOR, Role.MEMBER}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_memberships")
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "company"), name="unique_user_company_membership"),
        ]
        ordering = ["user__username", "company__name"]

    def clean(self) -> None:
        if self.role in self.PLATFORM_ROLES and self.company_id:
            raise ValidationError({"company": "Platform roles must not be assigned to a company."})
        if self.role in self.COMPANY_ROLES and not self.company_id:
            raise ValidationError({"company": "Company roles require a company."})

    def __str__(self) -> str:
        scope = self.company.name if self.company else "Platform"
        return f"{self.user} — {self.get_role_display()} ({scope})"


class ExternalDataSource(models.Model):
    class SourceType(models.TextChoices):
        HTTP_API = "http", "HTTP API"
        TELEGRAM = "telegram", "Telegram"
        RSS = "rss", "RSS Feed"
        INTERNAL = "internal", "Internal data"
        WEB = "web", "صفحه وب"

    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.CASCADE, related_name="external_data_sources")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_sources")
    category = models.CharField(max_length=16, choices=[("price", "قیمت"), ("news", "اخبار"), ("weather", "آب‌وهوا"), ("text", "متن")], default="price")
    unit = models.CharField(max_length=40, blank=True)
    ttl_seconds = models.PositiveIntegerField(default=300)
    extraction_pattern = models.CharField(max_length=500, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=64, choices=SourceType.choices, default=SourceType.HTTP_API)
    display_key = models.CharField(max_length=128)
    endpoint_url = models.URLField(max_length=500, blank=True)
    refresh_interval_seconds = models.PositiveIntegerField(default=900)
    credential_reference = models.CharField(max_length=128, blank=True)
    title_path = models.CharField(max_length=255, blank=True)
    value_path = models.CharField(max_length=255, blank=True)
    image_path = models.CharField(max_length=255, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=("company", "name"), name="unique_company_external_data_source_name"),
            models.UniqueConstraint(fields=("company", "display_key"), name="unique_company_external_data_source_display_key"),
            models.UniqueConstraint(fields=("display_key",), condition=models.Q(company__isnull=True), name="unique_global_source_key"),
        ]

    def __str__(self) -> str:
        return f"{self.company}: {self.name}"


class MessageCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        SENT = "sent", "Sent"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="message_campaigns")
    target_devices = models.ManyToManyField("WordPressDevice", related_name="message_campaigns", blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    price_list = models.ForeignKey("PriceList", null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns")
    last_error = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_message_campaigns")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.company}: {self.name}"


class SyncSource(models.TextChoices):
    WEBHOOK = "webhook", "Webhook"
    PULL = "pull", "Pull"


class SyncEntityType(models.TextChoices):
    DEVICE = "device", "Device"
    DATA_SOURCE = "data_source", "Data Source"
    UNKNOWN = "unknown", "Unknown"


class SyncEventStatus(models.TextChoices):
    PROCESSED = "processed", "Processed"
    IGNORED = "ignored", "Ignored"
    ERROR = "error", "Error"


class WordPressDevice(models.Model):
    class ProvisioningState(models.TextChoices):
        UNPROVISIONED = "unprovisioned", "Unprovisioned"
        PROVISIONED = "provisioned", "Provisioned"
        SUSPENDED = "suspended", "Suspended"

    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="devices")
    assigned_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_devices")
    recipient_name = models.CharField(max_length=150, blank=True)
    recipient_contact = models.CharField(max_length=150, blank=True)
    group_name = models.CharField(max_length=100, blank=True)
    customer_enabled = models.BooleanField(default=True)
    external_id = models.CharField(max_length=128, unique=True)
    customer_external_id = models.CharField(max_length=128, blank=True)
    serial_number = models.CharField(max_length=128, blank=True)
    hardware_model = models.CharField(max_length=128, blank=True)
    name = models.CharField(max_length=255, blank=True)
    plan = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    provisioning_state = models.CharField(
        max_length=32,
        choices=ProvisioningState.choices,
        default=ProvisioningState.UNPROVISIONED,
    )
    device_token_hash = models.CharField(max_length=128, blank=True, editable=False)
    device_token_created_at = models.DateTimeField(null=True, blank=True, editable=False)
    metadata = models.JSONField(default=dict, blank=True)
    custom_config = models.JSONField(default=dict, blank=True)
    effective_config = models.JSONField(default=dict, blank=True)
    ui_version = models.PositiveIntegerField(default=1)
    config_sync_pending = models.BooleanField(default=False, editable=False)
    last_wordpress_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.external_id} ({self.plan or 'no-plan'})"

    @property
    def normalized_plan(self) -> str:
        plan = (self.plan or "").strip().lower()
        if plan in {"pro", "vip", "premium", "professional"}:
            return "pro"
        return "simple"


class FirmwareRelease(models.Model):
    hardware_model = models.CharField(max_length=128, db_index=True)
    version = models.CharField(max_length=64)
    release_notes = models.TextField(blank=True)
    download_url = models.URLField(max_length=500, blank=True)
    firmware_file = models.FileField(upload_to="firmware/%Y/%m/", blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("hardware_model", "version"), name="unique_firmware_model_version"),
        ]
        ordering = ["-published_at", "-id"]

    def __str__(self) -> str:
        return f"{self.hardware_model} {self.version}"

    def clean(self) -> None:
        if not self.download_url and not self.firmware_file:
            raise ValidationError("Provide either a firmware upload or a download URL.")
        if self.download_url and self.firmware_file:
            raise ValidationError("Use either a firmware upload or a download URL, not both.")
        if self.download_url and len(self.checksum_sha256) != 64:
            raise ValidationError({"checksum_sha256": "A SHA-256 checksum is required for a remote download URL."})

    def save(self, *args, **kwargs):
        if self.firmware_file:
            digest = hashlib.sha256()
            if self.firmware_file._committed:
                self.firmware_file.open("rb")
                chunks = self.firmware_file.chunks()
            else:
                chunks = self.firmware_file.file.chunks()
            for chunk in chunks:
                digest.update(chunk)
            self.checksum_sha256 = digest.hexdigest()
            if self.firmware_file._committed:
                self.firmware_file.close()
        super().save(*args, **kwargs)


class FirmwareDeployment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DOWNLOADING = "downloading", "Downloading"
        INSTALLED = "installed", "Installed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    device = models.ForeignKey(WordPressDevice, on_delete=models.CASCADE, related_name="firmware_deployments")
    release = models.ForeignKey(FirmwareRelease, on_delete=models.PROTECT, related_name="deployments")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    reported_version = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    last_reported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("device", "release"), name="unique_device_firmware_deployment"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.device.external_id}: {self.release} ({self.status})"


class WordPressDataSource(models.Model):
    external_id = models.CharField(max_length=128, unique=True)
    key = models.CharField(max_length=128, blank=True)
    label = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    last_wordpress_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.key or self.external_id


class WordPressSyncEvent(models.Model):
    event_type = models.CharField(max_length=128)
    entity_type = models.CharField(max_length=32, choices=SyncEntityType.choices, default=SyncEntityType.UNKNOWN)
    entity_external_id = models.CharField(max_length=128, blank=True)
    source = models.CharField(max_length=16, choices=SyncSource.choices)
    payload = models.JSONField(default=dict, blank=True)
    payload_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=SyncEventStatus.choices, default=SyncEventStatus.PROCESSED)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class SyncNotification(models.Model):
    category = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    message = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    delivered = models.BooleanField(default=False)
    delivery_target = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PlanRule(models.Model):
    max_telegram_sources = models.PositiveIntegerField(default=0)
    min_refresh_seconds = models.PositiveIntegerField(default=60)
    can_send_messages = models.BooleanField(default=False)
    plan_name = models.CharField(max_length=64, unique=True)
    can_customize_ui = models.BooleanField(default=False)
    can_change_theme = models.BooleanField(default=False)
    can_add_pages = models.BooleanField(default=False)
    can_add_sources = models.BooleanField(default=False)
    max_pages = models.PositiveIntegerField(default=0)
    max_elements_per_page = models.PositiveIntegerField(default=0)
    max_sources = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.plan_name


class DeviceProfile(models.Model):
    device = models.OneToOneField(WordPressDevice, on_delete=models.CASCADE, related_name="profile")
    theme_name = models.CharField(max_length=64, default="dark")
    primary_color = models.CharField(max_length=16, default="#00B7FF")
    secondary_color = models.CharField(max_length=16, default="#FFFFFF")
    background_color = models.CharField(max_length=16, default="#000000")
    layout_mode = models.CharField(max_length=64, default="dashboard")
    refresh_interval_ms = models.PositiveIntegerField(default=60000)
    custom_config = models.JSONField(default=dict, blank=True)
    effective_config = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile for {self.device.external_id}"


class UITemplate(models.Model):
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=32, default="1.0")
    plan_type = models.CharField(max_length=32, default="simple")
    default_theme = models.JSONField(default=dict, blank=True)
    default_screen = models.JSONField(default=dict, blank=True)
    default_rules = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class UIPage(models.Model):
    template = models.ForeignKey(UITemplate, on_delete=models.CASCADE, related_name="pages")
    page_key = models.CharField(max_length=64)
    page_type = models.CharField(max_length=64)
    priority = models.PositiveIntegerField(default=0)
    refresh_interval_ms = models.PositiveIntegerField(default=60000)
    visible_when = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self) -> str:
        return f"{self.template.name}:{self.page_key}"


class UIElement(models.Model):
    page = models.ForeignKey(UIPage, on_delete=models.CASCADE, related_name="elements")
    element_type = models.CharField(max_length=64)
    label = models.CharField(max_length=128, blank=True)
    source_key = models.CharField(max_length=128, blank=True)
    x = models.PositiveIntegerField(default=0)
    y = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    font_size = models.CharField(max_length=32, blank=True)
    color = models.CharField(max_length=16, blank=True)
    style = models.JSONField(default=dict, blank=True)
    z_index = models.IntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["z_index", "id"]

    def __str__(self) -> str:
        return f"{self.page.page_key}:{self.element_type}"

class ServiceHealth(models.Model):
    SERVICE_CHOICES = [
        ("api", "API"),
        ("db", "Database"),
        ("redis", "Redis"),
        ("mqtt", "MQTT"),
        ("worker", "Celery Worker"),
    ]

    STATUS_CHOICES = [
        ("up", "Up"),
        ("down", "Down"),
        ("degraded", "Degraded"),
    ]

    service_name = models.CharField(max_length=64, choices=SERVICE_CHOICES, unique=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="up")
    response_time_ms = models.PositiveIntegerField(default=0)
    last_check_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)
    check_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Service Health"
        verbose_name_plural = "Service Health"
        ordering = ["service_name"]

    def __str__(self) -> str:
        return f"{self.get_service_name_display()} - {self.status}"


class DeviceStatus(models.Model):
    STATUS_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
        ("updating", "Updating"),
        ("error", "Error"),
    ]

    device = models.OneToOneField(WordPressDevice, on_delete=models.CASCADE, related_name="status")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="offline")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_config_version = models.PositiveIntegerField(default=0)
    firmware_version = models.CharField(max_length=64, blank=True)
    signal_strength = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Device Status"
        verbose_name_plural = "Device Status"

    def __str__(self) -> str:
        return f"{self.device.external_id} - {self.status}"

from core.platform_models import (Integration, PlatformSettings, DevicePreference, SourceSelection, PriceList, PriceItem, CampaignDelivery, AuditEvent, ResourceSnapshot)  # noqa: E402,F401
