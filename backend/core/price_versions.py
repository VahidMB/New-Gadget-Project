"""Atomic publication and bounded Excel ingestion; no spreadsheet execution."""
import io
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from core.models import PriceList, PriceRelease, PriceItem, ProductSample

UNITS = ['تومان', 'ریال', 'USD', 'EUR', 'GBP', 'AED', 'USDT', 'BTC', 'گرم', 'کیلوگرم', 'عدد']


def decimal_price(value, allow_negative=False):
    try:
        result = Decimal(str(value).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(',', '').replace('٬', '').replace('٫', '.'))
        if not result.is_finite() or (result < 0 and not allow_negative) or abs(result) >= Decimal('1e16') or result.as_tuple().exponent < -8:
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise ValidationError('قیمت باید عدد غیرمنفی با حداکثر ۸ رقم اعشار باشد.')


def validate_items(rows, scheduled_at):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ValidationError('هر نسخه باید بین ۱ تا ۵۰۰۰ کالا داشته باشد.')
    output, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError('ردیف کالا نامعتبر است.')
        code, name = str(row.get('code', '')).strip(), str(row.get('name', '')).strip()
        if not code or len(code) > 64 or code in seen or not name or len(name) > 150:
            raise ValidationError('شناسه/نام خالی، طولانی یا تکراری است.')
        unit = str(row.get('unit', '')).strip()
        if not unit or len(unit) > 32:
            raise ValidationError('واحد قیمت را مشخص کنید.')
        try:
            until = parse_datetime(str(row.get('valid_until', '')))
        except ValueError:
            until = None
        if not until or timezone.is_naive(until) or until <= scheduled_at:
            raise ValidationError('اعتبار هر قیمت باید با منطقه زمانی و بعد از زمان انتشار باشد.')
        output.append({'code': code, 'name': name, 'amount': format(decimal_price(row.get('amount')), 'f'), 'unit': unit, 'valid_until': until.isoformat()})
        seen.add(code)
    return output


@transaction.atomic
def schedule_release(price_list, rows, scheduled_at, user):
    locked = PriceList.objects.select_for_update().get(pk=price_list.pk)
    if timezone.is_naive(scheduled_at):
        raise ValidationError('زمان انتشار باید دارای منطقه زمانی باشد.')
    rows = validate_items(rows, scheduled_at)
    latest = locked.releases.order_by('-number').first()
    release = PriceRelease.objects.create(price_list=locked, number=(latest.number if latest else 0)+1, items=rows, scheduled_at=scheduled_at, created_by=user)
    return release


@transaction.atomic
def activate_due_release(pk):
    release = PriceRelease.objects.select_related('price_list').get(pk=pk)
    price_list = PriceList.objects.select_for_update().get(pk=release.price_list_id)
    release = PriceRelease.objects.select_for_update().get(pk=pk)
    now = timezone.now()
    if release.cancelled or release.published_at or release.scheduled_at > now:
        return False
    # Scheduled time defines ordering; a late retry must not roll back a newer effective release.
    newer = price_list.releases.filter(published_at__isnull=False, scheduled_at__gt=release.scheduled_at).exists()
    newer |= price_list.releases.filter(published_at__isnull=False, scheduled_at=release.scheduled_at, number__gt=release.number).exists()
    if newer:
        release.cancelled = True
        release.save(update_fields=['cancelled'])
        return False
    for row in release.items:
        item = PriceItem.objects.filter(price_list=price_list, code=row['code']).first()
        amount = decimal_price(row['amount'])
        latest = item.history.order_by('-observed_at', '-id').first() if item else None
        values = {'name': row['name'], 'amount': amount, 'unit': row['unit'], 'valid_until': parse_datetime(row['valid_until']), 'updated_at': now}
        if item:
            PriceItem.objects.filter(pk=item.pk).update(**values)
        else:
            item = PriceItem(price_list=price_list, code=row['code'], **values)
            item._release_publication = True
            item.save()
        if latest is None or latest.amount != amount or latest.unit != row['unit']:
            ProductSample.objects.create(item=item, release=release, observed_at=now, amount=amount, unit=row['unit'])
    release.published_at = now
    release.save(update_fields=['published_at'])
    PriceList.objects.filter(pk=price_list.pk).update(revision=price_list.revision+1, updated_at=now)
    return True


def current_release(price_list):
    return price_list.releases.filter(published_at__isnull=False, cancelled=False).order_by('-scheduled_at', '-number').first()


def visible_release_items(release):
    now = timezone.now()
    return [{**row, 'amount': row['amount'] if parse_datetime(row['valid_until']) > now else None,
             'status': 'fresh' if parse_datetime(row['valid_until']) > now else 'expired',
             'updated_at': release.published_at.isoformat()} for row in release.items]


def read_xlsx(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError('حداکثر اندازه فایل Excel پنج مگابایت است.')
    try:
        with zipfile.ZipFile(io.BytesIO(upload.read())) as archive:
            infos = archive.infolist()
            if len(infos) > 300 or sum(i.file_size for i in infos) > 20 * 1024 * 1024:
                raise ValidationError('فایل فشرده بیش از حد بزرگ است.')
            def xml(name):
                raw = archive.read(name)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                    raise ValidationError('ساختار XML مجاز نیست.')
                return ET.fromstring(raw)
            ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(t.text or '' for t in e.findall('.//m:t', ns)) for e in xml('xl/sharedStrings.xml').findall('m:si', ns)]
            names = sorted(n for n in archive.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))
            if len(names) != 1:
                raise ValidationError('یک فایل Excel با دقیقاً یک شیت داده بارگذاری کنید.')
            rows = []
            for r in xml(names[0]).findall('.//m:sheetData/m:row', ns):
                values = {}
                for cell in r.findall('m:c', ns):
                    if cell.find('m:f', ns) is not None:
                        raise ValidationError('فرمول مجاز نیست؛ مقادیر نهایی را در Excel جای‌گذاری کنید.')
                    ref = cell.attrib.get('r', '')
                    column = ''.join(c for c in ref if c.isalpha())
                    index = 0
                    for c in column:
                        index = index*26 + ord(c.upper())-64
                    if not 1 <= index <= 30:
                        raise ValidationError('حداکثر ۳۰ ستون مجاز است.')
                    val = cell.find('m:v', ns)
                    value = val.text if val is not None and val.text else ''
                    if cell.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//m:t', ns))
                    if len(value) > 2000:
                        raise ValidationError('مقدار سلول بیش از حد طولانی است.')
                    values[index-1] = value
                if values:
                    rows.append(values)
                if len(rows) > 5001:
                    raise ValidationError('حداکثر ۵۰۰۰ کالا مجاز است.')
            if len(rows) < 2:
                raise ValidationError('سطر عنوان و حداقل یک کالا لازم است.')
            width = max(rows[0])+1
            if any(max(row) >= width for row in rows[1:]):
                raise ValidationError('برای تمام ستون‌های دارای داده عنوان وارد کنید.')
            columns = [rows[0].get(i, '') for i in range(width)]
            if any(not c for c in columns) or len(set(columns)) != len(columns):
                raise ValidationError('عنوان ستون‌ها نباید خالی یا تکراری باشد.')
            return columns, [[row.get(i, '') for i in range(width)] for row in rows[1:]]
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, ValueError):
        raise ValidationError('فایل XLSX معتبر نیست.') from None
