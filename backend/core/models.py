from django.db import models


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
    external_id = models.CharField(max_length=128, unique=True)
    customer_external_id = models.CharField(max_length=128, blank=True)
    serial_number = models.CharField(max_length=128, blank=True)
    name = models.CharField(max_length=255, blank=True)
    plan = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    custom_config = models.JSONField(default=dict, blank=True)
    effective_config = models.JSONField(default=dict, blank=True)
    ui_version = models.PositiveIntegerField(default=1)
    last_wordpress_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.external_id} ({self.plan or 'no-plan'})"

    @property
    def normalized_plan(self) -> str:
        plan = (self.plan or "").strip().lower()
        if plan in {"pro", "vip", "premium"}:
            return "pro"
        return "simple"


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

    service_name = models.CharField(max_length=64, choices=SERVICE_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="up")
    response_time_ms = models.PositiveIntegerField(default=0)
    last_check_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)
    check_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ["service_name"]
        verbose_name_plural = "Service Health"

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
    battery_level = models.PositiveIntegerField(default=0)
    signal_strength = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Device Status"

    def __str__(self) -> str:
        return f"{self.device.external_id} - {self.status}"