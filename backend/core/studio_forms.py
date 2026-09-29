import hashlib
import io
import struct
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.platform_forms import PersianModelForm
from core.models import (DisplayProfile, DisplayAsset, DisplayTemplate, DisplayAssignment, DisplayPreference,
                         City, SourceField, OperationsPolicy, Integration)


class ProfileForm(PersianModelForm):
    class Meta:
        model = DisplayProfile
        fields = '__all__'
        labels = {'width': 'عرض (پیکسل)', 'height': 'ارتفاع (پیکسل)', 'diagonal_inches': 'اندازه (اینچ)',
                  'max_elements': 'سقف عناصر', 'max_chart_points': 'سقف نقاط نمودار',
                  'supports_glow': 'پشتیبانی از درخشش', 'supports_animation': 'پشتیبانی از جلوه متحرک'}


class AssetForm(PersianModelForm):
    class Meta:
        model = DisplayAsset
        fields = ['name', 'kind', 'file']
        labels = {'file': 'تصویر PNG/JPEG/GIF یا فونت TTF'}
    def clean(self):
        data = super().clean()
        upload = data.get('file')
        if not upload:
            return data
        if upload.size > 4*1024*1024:
            raise ValidationError('حجم فایل باید کمتر از ۴ مگابایت باشد.')
        raw = upload.read()
        upload.seek(0)
        if data.get('kind') == 'image':
            try:
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in ['PNG', 'JPEG', 'GIF'] or image.width > 1920 or image.height > 1920 or getattr(image, 'n_frames', 1) > 120:
                        raise ValueError
                    self.instance.animated = getattr(image, 'n_frames', 1) > 1
                    extension = {'PNG': '.png', 'JPEG': '.jpg', 'GIF': '.gif'}[image.format]
                    image.verify()
            except Exception:
                raise ValidationError('تصویر معتبر PNG/JPEG/GIF با ابعاد حداکثر ۱۹۲۰ و حداکثر ۱۲۰ فریم لازم است.') from None
        else:
            if raw[:4] != b'\x00\x01\x00\x00' or len(raw) < 12:
                raise ValidationError('فونت TrueType معتبر لازم است.')
            count = struct.unpack('>H', raw[4:6])[0]
            if not 1 <= count <= 100 or len(raw) < 12+count*16:
                raise ValidationError('ساختار فونت نامعتبر است.')
            for offset in range(12, 12+count*16, 16):
                start, length = struct.unpack('>II', raw[offset+8:offset+16])
                if start+length > len(raw):
                    raise ValidationError('جدول فونت ناقص است.')
        import uuid
        upload.name = str(uuid.uuid4()) + (extension if data.get('kind') == 'image' else '.ttf')
        self.instance.sha256 = hashlib.sha256(raw).hexdigest()
        return data


class TemplateForm(PersianModelForm):
    class Meta:
        model = DisplayTemplate
        fields = ['name', 'key', 'profile', 'kind']
        labels = {'key': 'شناسه ثابت قالب', 'profile': 'پروفایل نمایشگر', 'kind': 'کاربرد قالب'}


class AssignmentForm(PersianModelForm):
    class Meta:
        model = DisplayAssignment
        fields = ['version', 'scope', 'plan', 'company', 'user', 'device', 'position', 'active']
        labels = {'version': 'نسخه منتشرشده', 'scope': 'نوع مخاطب', 'plan': 'محدودیت پلن (اختیاری مگر مخاطب پلن)', 'user': 'کاربر', 'device': 'گجت', 'position': 'ترتیب صفحه', 'active': 'فعال'}
    def clean(self):
        data = super().clean()
        scope = data.get('scope')
        if scope in ['plan', 'company', 'user', 'device'] and not data.get(scope):
            self.add_error(scope, 'مخاطب این تخصیص را انتخاب کنید.')
        for name in ['company', 'user', 'device']:
            if scope != name:
                data[name] = None
        return data


class CityForm(PersianModelForm):
    class Meta:
        model = City
        fields = '__all__'
        labels = {'country': 'کشور', 'latitude': 'عرض جغرافیایی', 'longitude': 'طول جغرافیایی', 'active': 'فعال'}


class DisplayPreferenceForm(PersianModelForm):
    class Meta:
        model = DisplayPreference
        fields = ['city', 'page_seconds', 'items_per_page', 'item_seconds', 'resume_seconds', 'automatic', 'touch_short', 'touch_long']
        labels = {'city': 'شهر نصب گجت', 'page_seconds': 'مدت نمایش هر صفحه (ثانیه)', 'items_per_page': 'تعداد کالا در هر نما (محدود به ظرفیت طرح)', 'item_seconds': 'مدت نمایش هر دسته کالا (ثانیه)', 'resume_seconds': 'بازگشت به گردش خودکار پس از لمس (ثانیه)', 'automatic': 'گردش خودکار', 'touch_short': 'لمس کوتاه', 'touch_long': 'لمس طولانی'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['city'].queryset = City.objects.filter(active=True)


class SourceFieldForm(PersianModelForm):
    class Meta:
        model = SourceField
        exclude = ['source']
        labels = {'key': 'شناسه ثابت مقدار', 'label': 'عنوان', 'path': 'مسیر مقدار', 'numeric': 'مقدار عددی', 'keep_history': 'ثبت تاریخچه برای نمودار', 'timestamp_path': 'مسیر زمان ISO/Unix (اختیاری)', 'open_path': 'مسیر Open', 'high_path': 'مسیر High', 'low_path': 'مسیر Low', 'close_path': 'مسیر Close', 'provider_timeframe_seconds': 'تایم‌فریم کندل ارائه‌دهنده'}
    def clean(self):
        data = super().clean()
        if data.get('keep_history') and not data.get('numeric'):
            self.add_error('numeric', 'ثبت تاریخچه نمودار نیازمند مقدار عددی است.')
        ohlc = [data.get(k+'_path') for k in ['open', 'high', 'low', 'close']]
        if any(ohlc) and (not all(ohlc) or not data.get('timestamp_path') or not data.get('provider_timeframe_seconds')):
            raise ValidationError('برای OHLC هر چهار مسیر، مسیر زمان و تایم‌فریم کندل لازم است.')
        return data


class ExcelForm(forms.Form):
    file = forms.FileField(label='فایل Excel (.xlsx)، یک شیت، سطر اول عنوان ستون‌ها')


class ImportMappingForm(forms.Form):
    code = forms.ChoiceField(label='ستون شناسه کالا')
    name = forms.ChoiceField(label='ستون نام کالا')
    amount = forms.ChoiceField(label='ستون قیمت')
    unit_column = forms.ChoiceField(label='ستون واحد (اختیاری)', required=False)
    unit = forms.CharField(label='واحد پیش‌فرض', max_length=32, initial='تومان')
    scheduled_at = forms.DateTimeField(label='زمان انتشار', initial=timezone.now, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    valid_until = forms.DateTimeField(label='اعتبار قیمت‌ها تا', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    confirm = forms.BooleanField(label='پیش‌نمایش ردیف‌ها و واحدها را بررسی کرده‌ام؛ نسخه کامل لیست منتشر شود.')
    def __init__(self, *args, columns, **kwargs):
        super().__init__(*args, **kwargs)
        for key in ['code', 'name', 'amount', 'unit_column']:
            self.fields[key].choices = ([('', 'واحد پیش‌فرض')] if key == 'unit_column' else []) + [(str(i), c) for i, c in enumerate(columns)]
    def clean(self):
        data = super().clean()
        selected = [data.get(k) for k in ['code', 'name', 'amount']]
        if len(set(selected)) != 3:
            raise ValidationError('شناسه، نام و قیمت باید ستون‌های متفاوت باشند.')
        if data.get('valid_until') and data.get('scheduled_at') and data['valid_until'] <= data['scheduled_at']:
            raise ValidationError('اعتبار باید بعد از انتشار باشد.')
        return data


class OperationsForm(PersianModelForm):
    class Meta:
        model = OperationsPolicy
        exclude = ['id', 'next_backup']
        labels = {'backup_enabled': 'پشتیبان‌گیری خودکار', 'backup_hours': 'فاصله پشتیبان‌گیری (ساعت)', 'sms_enabled': 'فعال‌سازی هشدار پیامکی', 'sms_integration': 'اتصال HTTPS سرویس پیامک', 'sms_recipient': 'شماره مدیر', 'sms_recipient_key': 'نام فیلد گیرنده در API', 'sms_message_key': 'نام فیلد متن در API', 'sms_template': 'متن هشدار ({service} و {state})', 'weather_integration': 'اتصال منبع آب‌وهوا', 'weather_url': 'آدرس آب‌وهوا با {lat} و {lon}', 'weather_value_path': 'مسیر دما', 'weather_condition_path': 'مسیر شرح وضعیت', 'weather_unit': 'واحد دما', 'weather_seconds': 'فاصله دریافت آب‌وهوا (ثانیه)'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ['sms_integration', 'weather_integration']:
            self.fields[name].queryset = Integration.objects.filter(company__isnull=True, is_active=True, kind='provider')
    def clean(self):
        data = super().clean()
        if data.get('sms_enabled') and (not data.get('sms_integration') or not data.get('sms_recipient')):
            raise ValidationError('برای پیامک، اتصال و شماره گیرنده را تعیین کنید.')
        if data.get('sms_recipient_key') == data.get('sms_message_key'):
            raise ValidationError('نام فیلد گیرنده و متن باید متفاوت باشند.')
        if data.get('sms_enabled') and not data['sms_integration'].endpoint.startswith('https://'):
            raise ValidationError('اتصال پیامک باید HTTPS باشد.')
        return data


class PublishPricesForm(forms.Form):
    scheduled_at = forms.DateTimeField(label='زمان انتشار نسخه کامل', initial=timezone.now, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    confirm = forms.BooleanField(label='انتشار کل اقلام فعلی را تأیید می‌کنم')
