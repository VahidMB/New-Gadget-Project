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
