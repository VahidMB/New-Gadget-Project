from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator


class PlatformSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField(max_length=100, default="گجت من")
    public_base_url = models.URLField(blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Tehran")
    setup_complete = models.BooleanField(default=False)
    heartbeat_timeout = models.PositiveIntegerField(default=300, validators=[MinValueValidator(30)])
    audit_retention_days = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(365)])
    test_mode = models.BooleanField(default=True)
    cleanup_enabled = models.BooleanField(default=True)
    device_mqtt_host = models.CharField(max_length=255, blank=True)
    device_mqtt_port = models.PositiveIntegerField(default=443, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    device_mqtt_transport = models.CharField(max_length=16, choices=[("websockets", "WebSocket امن"), ("tcp", "MQTT TCP")], default="websockets")
    device_mqtt_tls = models.BooleanField(default=True)
    device_mqtt_path = models.CharField(max_length=128, default="/mqtt")
    device_heartbeat_seconds = models.PositiveIntegerField(default=60, validators=[MinValueValidator(10), MaxValueValidator(3600)])
    wordpress_poll_seconds = models.PositiveIntegerField(default=900, validators=[MinValueValidator(30), MaxValueValidator(86400)])
    wordpress_signature_max_age = models.PositiveIntegerField(default=300, validators=[MinValueValidator(30), MaxValueValidator(900)])
    managed_tls = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class Integration(models.Model):
    key = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=24, choices=[("wordpress", "WordPress"), ("mqtt", "MQTT"), ("telegram", "تلگرام"), ("provider", "منبع داده"), ("monitor", "پایش سرور"), ("notifications", "اعلان‌ها"), ("metrics", "توکن پایش")])
    company = models.ForeignKey("core.Company", null=True, blank=True, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=500, blank=True)
    username = models.CharField(max_length=128, blank=True)
    port = models.PositiveIntegerField(default=8883, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    use_tls = models.BooleanField(default=True)
    options = models.JSONField(default=dict, blank=True)
    encrypted_secret = models.TextField(blank=True, editable=False)
    encrypted_webhook_secret = models.TextField(blank=True, editable=False)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_secret(self, value, webhook=False):
        from core.secrets import encrypt
        setattr(self, "encrypted_webhook_secret" if webhook else "encrypted_secret", encrypt(value))

    def secret(self, webhook=False):
        from core.secrets import decrypt
        return decrypt(self.encrypted_webhook_secret if webhook else self.encrypted_secret)

    def __str__(self):
        return self.name


class DevicePreference(models.Model):
    device = models.OneToOneField("core.WordPressDevice", on_delete=models.CASCADE, related_name="preferences")
    theme = models.CharField(max_length=16, choices=[("navy", "سرمه‌ای"), ("light", "روشن"), ("carbon", "کربن")], default="navy")
    rotation_seconds = models.PositiveIntegerField(default=300, validators=[MinValueValidator(5), MaxValueValidator(86400)])
    live_updates = models.BooleanField(default=True)
    custom_primary = models.CharField(max_length=7, blank=True, validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "رنگ را با فرمت #RRGGBB وارد کنید.")])
    updated_at = models.DateTimeField(auto_now=True)


class SourceSelection(models.Model):
    device = models.ForeignKey("core.WordPressDevice", on_delete=models.CASCADE, related_name="source_selections")
    source = models.ForeignKey("core.ExternalDataSource", on_delete=models.CASCADE, related_name="selections")
    position = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["device", "source"], name="unique_device_source")]


class PriceList(models.Model):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="price_lists")
    name = models.CharField(max_length=150)
    revision = models.PositiveIntegerField(default=1)
    target_devices = models.ManyToManyField("core.WordPressDevice", blank=True, related_name="price_lists")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class PriceItem(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=64)
    disposable = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=32, default="تومان")
    valid_until = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["price_list", "code"], name="unique_price_item_code")]
        ordering = ["id"]


class CampaignDelivery(models.Model):
    campaign = models.ForeignKey("core.MessageCampaign", on_delete=models.CASCADE, related_name="deliveries")
    device = models.ForeignKey("core.WordPressDevice", on_delete=models.CASCADE)
    delivered_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "device"], name="unique_campaign_delivery")]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    object_label = models.CharField(max_length=180)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ResourceSnapshot(models.Model):
    service = models.CharField(max_length=64, unique=True)
    cpu_percent = models.FloatField(null=True)
    memory_bytes = models.BigIntegerField(null=True)
    disk_bytes = models.BigIntegerField(null=True)
    network_rx_bytes = models.BigIntegerField(null=True)
    network_tx_bytes = models.BigIntegerField(null=True)
    sampled_at = models.DateTimeField(auto_now=True)
    origin = models.CharField(max_length=100, default="collector")


class BuzzerRule(models.Model):
    device = models.ForeignKey("core.WordPressDevice", on_delete=models.CASCADE, related_name="buzzer_rules")
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    scope = models.CharField(max_length=16, choices=[("all", "همه اطلاعات"), ("source", "یک منبع"), ("price", "قیمت یک کالا"), ("messages", "پیام‌های شرکت")], default="all")
    source = models.ForeignKey("core.ExternalDataSource", null=True, blank=True, on_delete=models.SET_NULL)
    price_item = models.ForeignKey(PriceItem, null=True, blank=True, on_delete=models.SET_NULL)
    trigger = models.CharField(max_length=16, choices=[("new", "اطلاعات جدید یا تغییر مقدار"), ("percent", "نوسان درصدی"), ("absolute", "نوسان به مقدار مشخص"), ("above", "عبور از سقف"), ("below", "عبور از کف")], default="new")
    direction = models.CharField(max_length=8, choices=[("both", "افزایش و کاهش"), ("up", "فقط افزایش"), ("down", "فقط کاهش")], default="both")
    threshold = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True, validators=[MinValueValidator(0)])
    window_seconds = models.PositiveIntegerField(default=0)
    notify_first = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(default=300, validators=[MinValueValidator(50), MaxValueValidator(3000)])
    repeat = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(5)])
    gap_ms = models.PositiveIntegerField(default=200, validators=[MinValueValidator(50), MaxValueValidator(3000)])
    cooldown_seconds = models.PositiveIntegerField(default=60, validators=[MinValueValidator(5), MaxValueValidator(86400)])
    max_per_hour = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1), MaxValueValidator(120)])
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)
    weekdays = models.JSONField(default=list, blank=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class BuzzerEvent(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey("core.WordPressDevice", on_delete=models.PROTECT, related_name="buzzer_events")
    rule = models.ForeignKey(BuzzerRule, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=100)
    item_key = models.CharField(max_length=150)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)


    class Meta:
        indexes = [models.Index(fields=["device", "expires_at"], name="buzzer_device_expiry"), models.Index(fields=["rule", "created_at"], name="buzzer_rule_time")]


class DeviceBrokerCredential(models.Model):
    device = models.OneToOneField("core.WordPressDevice", on_delete=models.CASCADE, related_name="broker_credential")
    encrypted_password = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
