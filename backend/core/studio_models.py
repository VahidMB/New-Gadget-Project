"""Versioned display contracts, published prices and operational state."""
import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class DisplayProfile(models.Model):
    name = models.CharField(max_length=100)
    width = models.PositiveIntegerField(default=480, validators=[MinValueValidator(128), MaxValueValidator(1920)])
    height = models.PositiveIntegerField(default=320, validators=[MinValueValidator(128), MaxValueValidator(1920)])
    diagonal_inches = models.DecimalField(max_digits=4, decimal_places=1, default=3.5)
    max_elements = models.PositiveIntegerField(default=40, validators=[MinValueValidator(1), MaxValueValidator(100)])
    max_chart_points = models.PositiveIntegerField(default=120, validators=[MinValueValidator(2), MaxValueValidator(500)])
    supports_glow = models.BooleanField(default=False)
    supports_animation = models.BooleanField(default=False)
    def __str__(self):
        return f'{self.name} ({self.width}×{self.height})'


class DisplayAsset(models.Model):
    name = models.CharField(max_length=100)
    file = models.FileField(upload_to='display-assets/%Y/%m/')
    kind = models.CharField(max_length=16, choices=[('image', 'تصویر'), ('font', 'فونت')])
    sha256 = models.CharField(max_length=64)
    animated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.name


class DisplayTemplate(models.Model):
    name = models.CharField(max_length=100)
    key = models.SlugField(unique=True)
    profile = models.ForeignKey(DisplayProfile, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=[('page', 'صفحه'), ('fallback', 'جایگزین مقدار'), ('offline', 'قطع ارتباط'), ('boot', 'شروع')], default='page')
    draft = models.JSONField(default=dict, blank=True)
    draft_revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


class DisplayVersion(models.Model):
    template = models.ForeignKey(DisplayTemplate, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    document = models.JSONField()
    checksum = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'number'], name='unique_display_version')]
    def __str__(self):
        return f'{self.template.name} / {self.number}'


class DisplayAssignment(models.Model):
    version = models.ForeignKey(DisplayVersion, on_delete=models.PROTECT)
    scope = models.CharField(max_length=12, choices=[('global', 'عمومی'), ('plan', 'پلن'), ('company', 'شرکت'), ('user', 'کاربر'), ('device', 'دستگاه')])
    plan = models.CharField(max_length=8, choices=[('simple', 'ساده'), ('pro', 'VIP')], blank=True)
    company = models.ForeignKey('core.Company', null=True, blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    device = models.ForeignKey('core.WordPressDevice', null=True, blank=True, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)


class City(models.Model):
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=60, default='ایران')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    active = models.BooleanField(default=True)
    def __str__(self):
        return f'{self.name}، {self.country}'


class DisplayPreference(models.Model):
    device = models.OneToOneField('core.WordPressDevice', on_delete=models.CASCADE, related_name='display_preferences')
    city = models.ForeignKey(City, null=True, blank=True, on_delete=models.SET_NULL)
    page_seconds = models.PositiveIntegerField(default=30, validators=[MinValueValidator(5), MaxValueValidator(3600)])
    items_per_page = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(20)])
    item_seconds = models.PositiveIntegerField(default=10, validators=[MinValueValidator(3), MaxValueValidator(3600)])
    resume_seconds = models.PositiveIntegerField(default=30, validators=[MinValueValidator(5), MaxValueValidator(3600)])
    automatic = models.BooleanField(default=True)
    touch_short = models.CharField(max_length=20, default='next_batch', choices=[('next_batch', 'دسته بعد'), ('next_page', 'صفحه بعد'), ('previous_batch', 'دسته قبل'), ('previous_page', 'صفحه قبل')])
    touch_long = models.CharField(max_length=20, default='next_page', choices=[('next_batch', 'دسته بعد'), ('next_page', 'صفحه بعد'), ('previous_batch', 'دسته قبل'), ('previous_page', 'صفحه قبل')])
    charts = models.JSONField(default=dict, blank=True)


class SourceField(models.Model):
    source = models.ForeignKey('core.ExternalDataSource', on_delete=models.CASCADE, related_name='data_fields')
    key = models.SlugField()
    label = models.CharField(max_length=100)
    path = models.CharField(max_length=255)
    unit = models.CharField(max_length=32, blank=True)
    numeric = models.BooleanField(default=False)
    keep_history = models.BooleanField(default=False)
    timestamp_path = models.CharField(max_length=255, blank=True)
    open_path = models.CharField(max_length=255, blank=True)
    high_path = models.CharField(max_length=255, blank=True)
    low_path = models.CharField(max_length=255, blank=True)
    close_path = models.CharField(max_length=255, blank=True)
    provider_timeframe_seconds = models.PositiveIntegerField(default=0, choices=[(0, "بدون کندل آماده"), (60, "۱ دقیقه"), (300, "۵ دقیقه"), (900, "۱۵ دقیقه"), (3600, "۱ ساعت"), (14400, "۴ ساعت"), (86400, "۱ روز")])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'key'], name='unique_source_field')]
    def __str__(self):
        return f'{self.source.name} / {self.label}'


class MarketSample(models.Model):
    field = models.ForeignKey(SourceField, on_delete=models.PROTECT, related_name='samples')
    observed_at = models.DateTimeField()
    value = models.DecimalField(max_digits=24, decimal_places=8)
    ohlc = models.JSONField(default=dict, blank=True)
    origin = models.CharField(max_length=12, default='sample')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['field', 'observed_at'], name='unique_market_sample')]
        indexes = [models.Index(fields=['field', 'observed_at'])]


class PriceRelease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    price_list = models.ForeignKey('core.PriceList', on_delete=models.PROTECT, related_name='releases')
    number = models.PositiveIntegerField()
    items = models.JSONField(default=list)
    scheduled_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['price_list', 'number'], name='unique_price_release')]


class ProductSample(models.Model):
    item = models.ForeignKey('core.PriceItem', on_delete=models.PROTECT, related_name='history')
    release = models.ForeignKey(PriceRelease, null=True, on_delete=models.PROTECT)
    observed_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    unit = models.CharField(max_length=32)
    class Meta:
        indexes = [models.Index(fields=['item', 'observed_at'])]


class ImportBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    price_list = models.ForeignKey('core.PriceList', on_delete=models.CASCADE)
    rows = models.JSONField()
    columns = models.JSONField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)


class DeviceReceipt(models.Model):
    device = models.ForeignKey('core.WordPressDevice', on_delete=models.CASCADE, related_name='display_receipts')
    revision = models.CharField(max_length=64)
    manifest = models.JSONField()
    offered_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['device', 'revision'], name='unique_device_receipt')]


class OperationsPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    backup_enabled = models.BooleanField(default=False)
    backup_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1), MaxValueValidator(720)])
    next_backup = models.DateTimeField(null=True, blank=True)
    sms_enabled = models.BooleanField(default=False)
    sms_integration = models.ForeignKey('core.Integration', null=True, blank=True, on_delete=models.SET_NULL)
    sms_recipient = models.CharField(max_length=100, blank=True)
    sms_recipient_key = models.CharField(max_length=64, default='to')
    sms_message_key = models.CharField(max_length=64, default='message')
    sms_template = models.TextField(default='Gadget: {service}: {state}')
    weather_integration = models.ForeignKey('core.Integration', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    weather_url = models.CharField(max_length=500, blank=True)
    weather_value_path = models.CharField(max_length=255, default='current.temperature_2m')
    weather_condition_path = models.CharField(max_length=255, blank=True)
    weather_unit = models.CharField(max_length=32, default='°C')
    weather_seconds = models.PositiveIntegerField(default=900, validators=[MinValueValidator(60), MaxValueValidator(86400)])


class OperationJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=[('backup', 'پشتیبان'), ('sms', 'پیامک')])
    key = models.CharField(max_length=180, unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    next_attempt = models.DateTimeField()
    lease_until = models.DateTimeField(null=True)
    result = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)


class OperationalAlert(models.Model):
    service = models.CharField(max_length=64, unique=True)
    active = models.BooleanField(default=False)
    generation = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
