"""One validated display contract shared by firmware and the browser simulator."""
import hashlib
import json
import re
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from core.runtime import platform_settings
from core.models import (DisplayAsset, DisplayTemplate, DisplayVersion, DisplayAssignment, DisplayPreference,
                         DeviceReceipt, SourceField, PriceItem, MarketSample, ProductSample)
from core.access import ancestor_company_ids, rule_for
from core.content import device_content

TIMEFRAMES = [60, 300, 900, 3600, 14400, 86400]
KINDS = ['text', 'value', 'image', 'clock', 'weather', 'chart', 'prices', 'message']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f'{label}: عدد صحیح بین {minimum} و {maximum} لازم است.')
    return value


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValidationError('رنگ باید به شکل #RRGGBB باشد.')
    return value


def asset_id(value, kind):
    if value in [None, '', 0]:
        return None
    integer(value, 1, 2**31-1, 'فایل')
    if not DisplayAsset.objects.filter(pk=value, kind=kind).exists():
        raise ValidationError('فایل انتخاب‌شده وجود ندارد یا نوع آن مناسب نیست.')
    return value


def validate_document(template, raw):
    if not isinstance(raw, dict) or len(json.dumps(raw).encode()) > 128*1024:
        raise ValidationError('طرح نامعتبر یا بیش از حد بزرگ است.')
    p = template.profile
    p.full_clean()
    document = {'schema': 1, 'kind': template.kind, 'width': p.width, 'height': p.height,
                'profile_id': p.pk, 'background': color(raw.get('background', '#233b55')),
                'background_asset': asset_id(raw.get('background_asset'), 'image'),
                'duration_seconds': integer(raw.get('duration_seconds', 15), 3, 3600, 'زمان نمایش'), 'elements': []}
    elements = raw.get('elements', [])
    if not isinstance(elements, list) or len(elements) > p.max_elements:
        raise ValidationError('تعداد عناصر بیشتر از ظرفیت پروفایل است.')
    ids = set()
    for el in elements:
        if not isinstance(el, dict):
            raise ValidationError('عنصر نامعتبر است.')
        key = el.get('id', '')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', key) or key in ids:
            raise ValidationError('شناسه عنصر خالی یا تکراری است.')
        ids.add(key)
        kind = el.get('kind', 'text')
        if kind not in KINDS or (template.kind in ['fallback', 'boot', 'offline'] and kind in ['chart', 'prices', 'value', 'weather', 'message']):
            raise ValidationError('نوع عنصر در این قالب مجاز نیست.')
        item = {'id': key, 'kind': kind}
        for name, limit in [('x', p.width), ('y', p.height), ('width', p.width), ('height', p.height)]:
            item[name] = integer(el.get(name, 0), 0 if name in ['x', 'y'] else 1, limit, name)
        if item['x']+item['width'] > p.width or item['y']+item['height'] > p.height:
            raise ValidationError('عنصر از محدوده نمایشگر خارج است.')
        item['text'] = str(el.get('text', ''))[:500]
        item['color'] = color(el.get('color', '#ffffff'))
        item['fill'] = color(el.get('fill', '#233b55'))
        item['opacity'] = integer(el.get('opacity', 100), 0, 100, 'شفافیت')
        item['font_size'] = integer(el.get('font_size', 24), 8, 150, 'اندازه فونت')
        item['radius'] = integer(el.get('radius', 0), 0, 100, 'گردی')
        item['align'] = el.get('align', 'right')
        if item['align'] not in ['left', 'center', 'right']:
            raise ValidationError('ترازبندی نامعتبر است.')
        item['font_asset'] = asset_id(el.get('font_asset'), 'font')
        item['image_asset'] = asset_id(el.get('image_asset'), 'image')
        item['glow'] = integer(el.get('glow', 0), 0, 30, 'درخشش')
        item['glow_color'] = color(el.get('glow_color', '#4499ff'))
        item['pulse_ms'] = integer(el.get('pulse_ms', 0), 0, 10000, 'ضربان')
        if item['pulse_ms'] and item['pulse_ms'] < 500:
            raise ValidationError('دوره جلوه باید حداقل ۵۰۰ میلی‌ثانیه باشد.')
        if item['glow'] and not p.supports_glow or item['pulse_ms'] and not p.supports_animation:
            raise ValidationError('پروفایل نمایشگر از این جلوه پشتیبانی نمی‌کند.')
        item['decimals'] = integer(el.get('decimals', 0), 0, 8, 'اعشار')
        item['divisor'] = el.get('divisor', 1)
        if item['divisor'] not in [1, 10, 100, 1000]:
            raise ValidationError('ضریب نمایش نامعتبر است.')
        item['unit'] = str(el.get('unit', ''))[:32]
        item['show_updated'] = bool(el.get('show_updated', False))
        item['persian_digits'] = bool(el.get('persian_digits', True))
        item['fallback_text'] = str(el.get('fallback_text', 'اطلاعات در دسترس نیست'))[:150]
        fallback = el.get('fallback_version')
        if fallback:
            try:
                version = DisplayVersion.objects.select_related('template').get(pk=fallback, template__kind='fallback')
            except (DisplayVersion.DoesNotExist, ValueError, TypeError):
                raise ValidationError('نسخه قالب جایگزین معتبر نیست.') from None
            item['fallback'] = version.document
            item['fallback_version'] = version.pk
        if kind in ['value', 'chart']:
            field, product = el.get('field_id'), el.get('product_id')
            if bool(field) == bool(product):
                raise ValidationError('دقیقاً یک فیلد منبع یا کالا انتخاب کنید.')
            integer(field or product, 1, 2**31-1, 'شناسه داده')
            model = SourceField if field else PriceItem
            if not model.objects.filter(pk=field or product).exists():
                raise ValidationError('داده انتخاب‌شده وجود ندارد.')
            item['field_id'], item['product_id'] = field, product
        if kind == 'prices':
            from core.models import PriceList
            integer(el.get('price_list_id'), 1, 2**31-1, 'لیست قیمت')
            if not PriceList.objects.filter(pk=el.get('price_list_id')).exists():
                raise ValidationError('لیست قیمت را انتخاب کنید.')
            item['price_list_id'] = el['price_list_id']
            item['rows'] = integer(el.get('rows', 5), 1, 20, 'ظرفیت کالا')
        if kind == 'chart':
            allowed_types = el.get('allowed_types', ['line'])
            if not isinstance(allowed_types, list) or not allowed_types or any(t not in ['line', 'area', 'step', 'candle'] for t in allowed_types):
                raise ValidationError('نوع نمودار نامعتبر است.')
            if product and 'candle' in allowed_types:
                raise ValidationError('برای کالای شرکتی نمودار خطی، ناحیه‌ای یا پله‌ای انتخاب کنید.')
            if field:
                definition = SourceField.objects.get(pk=field)
                if 'candle' in allowed_types and not all([definition.open_path, definition.high_path, definition.low_path, definition.close_path, definition.provider_timeframe_seconds]):
                    raise ValidationError('نمودار کندلی به چهار مقدار OHLC و تایم‌فریم کندل منبع نیاز دارد.')
                if not definition.numeric or not definition.keep_history:
                    raise ValidationError('برای نمودار، فیلد عددی با ثبت تاریخچه لازم است.')
            timeframes = el.get('timeframes', [300, 900, 3600])
            if not isinstance(timeframes, list) or not timeframes or any(t not in TIMEFRAMES for t in timeframes):
                raise ValidationError('تایم‌فریم نامعتبر است.')
            if field and definition.provider_timeframe_seconds and any(t < definition.provider_timeframe_seconds or t % definition.provider_timeframe_seconds for t in timeframes):
                raise ValidationError('تایم‌فریم باید مضرب تایم‌فریم کندل ارائه‌دهنده باشد.')
            item.update({'allowed_types': allowed_types, 'timeframes': timeframes,
                         'chart_type': el.get('chart_type', allowed_types[0]),
                         'timeframe': el.get('timeframe', timeframes[0]),
                         'max_points': integer(el.get('max_points', 60), 2, p.max_chart_points, 'تعداد نقاط'),
                         'up_color': color(el.get('up_color', '#22c55e')), 'down_color': color(el.get('down_color', '#ef4444')),
                         'customizable': bool(el.get('customizable', False)), 'grid': bool(el.get('grid', True))})
            if item['chart_type'] not in allowed_types or item['timeframe'] not in timeframes:
                raise ValidationError('پیش‌فرض نمودار باید یکی از گزینه‌های مجاز باشد.')
        document['elements'].append(item)
    if not p.supports_animation and DisplayAsset.objects.filter(pk__in=manifest_assets({'pages': [document], 'special': {}}), animated=True).exists():
        raise ValidationError('این پروفایل از تصویر متحرک پشتیبانی نمی‌کند.')
    return document


@transaction.atomic
def publish_template(template_id, user, expected_revision):
    template = DisplayTemplate.objects.select_for_update().select_related('profile').get(pk=template_id)
    if template.draft_revision != expected_revision:
        raise ValidationError('طرح توسط فرد دیگری تغییر کرده است؛ دوباره بارگذاری کنید.')
    document = validate_document(template, template.draft)
    previous = template.versions.order_by('-number').first()
    return DisplayVersion.objects.create(template=template, number=(previous.number if previous else 0)+1,
                                         document=document, checksum=digest(document), created_by=user)


def assignments_for(device):
    company_ids = list(ancestor_company_ids(device.company_id))
    # Distance from the device company, not unordered ancestor set order.
    from core.models import Company
    depth, cursor, distance = {}, device.company_id, 0
    while cursor and cursor not in depth:
        depth[cursor] = distance
        cursor = Company.objects.filter(pk=cursor, is_active=True).values_list('parent_id', flat=True).first()
        distance += 1
    selected = {}
    for assignment in DisplayAssignment.objects.filter(active=True).select_related('version__template'):
        matches = assignment.scope == 'global' or (assignment.scope == 'plan' and assignment.plan == device.normalized_plan) or (assignment.scope == 'company' and assignment.company_id in company_ids) or (assignment.scope == 'user' and assignment.user_id == device.assigned_user_id) or (assignment.scope == 'device' and assignment.device_id == device.pk)
        if not matches:
            continue
        # A plan restriction on any assignment is always enforced.
        if assignment.plan and assignment.plan != device.normalized_plan:
            continue
        score = ({'global': 0, 'plan': 1, 'company': 2, 'user': 3, 'device': 4}[assignment.scope], -depth.get(assignment.company_id, 0), assignment.pk)
        kind = assignment.version.template.kind
        key = assignment.version.template.key if kind == 'page' else '__special__:'+kind
        if key not in selected or score > selected[key][0]:
            selected[key] = (score, assignment)
    return sorted([v[1] for v in selected.values()], key=lambda a: (a.position, a.pk))


def price_revision(row):
    return str(row['revision']) if isinstance(row['revision'], str) else digest(row['items'])


def preference_fingerprint(device):
    values = DisplayPreference.objects.filter(device=device).values().first()
    return digest(values or {})


def allowed_data(device):
    data = device_content(device)
    sources = {s['id']: s for s in data['sources']}
    lists = {row['id']: row for row in data['price_lists']}
    return data, sources, lists


def chart_points(field=None, product=None, timeframe=300, count=60):
    cutoff = timezone.now()-timezone.timedelta(seconds=timeframe*count)
    samples = MarketSample.objects.filter(field=field, observed_at__gte=cutoff) if field else ProductSample.objects.filter(item=product, observed_at__gte=cutoff)
    # Bound the read; dense series require DB-side rollups before raising capacity limits.
    samples = list(samples.order_by('-observed_at', '-id')[:20000])
    if product and samples:
        # Never combine different units on one price axis, including a later switch back.
        end = next((i for i, sample in enumerate(samples) if sample.unit != samples[0].unit), len(samples))
        samples = samples[:end]
    samples.reverse()
    buckets = {}
    for sample in samples:
        stamp = int(sample.observed_at.timestamp())//timeframe*timeframe
        value = sample.value if field else sample.amount
        bar = sample.ohlc if field and sample.ohlc else {'open': str(value), 'high': str(value), 'low': str(value), 'close': str(value)}
        if stamp not in buckets:
            buckets[stamp] = {'time': stamp, **bar, 'origin': sample.origin if field else 'product'}
        else:
            current = buckets[stamp]
            current['high'] = str(max(Decimal(current['high']), Decimal(bar['high'])))
            current['low'] = str(min(Decimal(current['low']), Decimal(bar['low'])))
            current['close'] = bar['close']
            if current['origin'] != (sample.origin if field else 'product'):
                current['origin'] = 'sample'
    now = timezone.now().timestamp()
    return [{**row, 'closed': row['time']+timeframe <= now} for row in list(buckets.values())[-count:]]


def chart_override(element, preference, key):
    if not element.get('customizable'):
        return element
    override = preference.charts.get(key, {}) if preference else {}
    if not isinstance(override, dict):
        return element
    result = dict(element)
    if override.get('chart_type') in element['allowed_types']:
        result['chart_type'] = override['chart_type']
    if override.get('timeframe') in element['timeframes']:
        result['timeframe'] = override['timeframe']
    if isinstance(override.get('max_points'), int) and 2 <= override['max_points'] <= element['max_points']:
        result['max_points'] = override['max_points']
    for name in ['up_color', 'down_color']:
        if re.fullmatch(r'#[0-9a-fA-F]{6}', str(override.get(name, ''))):
            result[name] = override[name]
    result['point_limit'] = element['max_points']
    return result


def build_manifest(device, assignments=None):
    content_data, sources, lists = allowed_data(device)
    preference = DisplayPreference.objects.select_related('city').filter(device=device).first()
    rule = rule_for(device.normalized_plan)
    pages, special, origins = [], {}, []
    assignments = assignments if assignments is not None else assignments_for(device)
    for assignment in assignments:
        version = assignment.version
        doc = json.loads(json.dumps(version.document))
        if doc['kind'] == 'fallback':
            continue
        if doc['kind'] == 'page' and len(pages) >= rule.max_pages:
            continue
        doc['elements'] = doc['elements'][:rule.max_elements_per_page]
        for index, el in enumerate(doc['elements']):
            key = f'{version.template.key}:{el["id"]}'
            el = chart_override(el, preference, key) if el['kind'] == 'chart' else el
            doc['elements'][index] = el
            el['preference_key'] = key
            value, fresh, points = None, False, []
            if el.get('field_id'):
                field = SourceField.objects.filter(pk=el['field_id']).first()
                source = sources.get(field.source_id) if field else None
                content = source.get('data') if source else None
                entry = (content or {}).get('fields', {}).get(field.key, {}) if field else {}
                value = entry.get('value')
                if not el.get('unit') and field:
                    el['unit'] = field.unit
                fresh = value is not None and bool(content)
                el['expires_at'] = (content or {}).get('expires_at')
                el['updated_at'] = entry.get('observed_at', (content or {}).get('observed_at'))
                if entry.get('observed_at'):
                    expires = parse_datetime(entry['observed_at'])+timezone.timedelta(seconds=field.source.ttl_seconds)
                    el['expires_at'] = min(expires, parse_datetime(el['expires_at'])).isoformat() if el['expires_at'] else expires.isoformat()
                    if expires <= timezone.now():
                        value, fresh = None, False
                if el['kind'] == 'chart' and source:
                    points = chart_points(field=field, timeframe=el['timeframe'], count=el['max_points'])
            elif el.get('product_id'):
                product = PriceItem.objects.filter(pk=el['product_id']).first()
                price_list = lists.get(product.price_list_id) if product else None
                row = next((r for r in (price_list or {}).get('items', []) if r['code'] == product.code), None) if product else None
                value = (row or {}).get('amount')
                if not el.get('unit') and row:
                    el['unit'] = row.get('unit', '')
                fresh = value is not None
                el['expires_at'] = (row or {}).get('valid_until')
                el['updated_at'] = (row or {}).get('updated_at')
                if el['kind'] == 'chart' and row:
                    points = chart_points(product=product, timeframe=el['timeframe'], count=el['max_points'])
            if el['kind'] in ['value', 'chart']:
                el['data'] = {'value': value, 'status': 'fresh' if fresh else 'unavailable', 'points': points}
            if el['kind'] == 'prices':
                price_list = lists.get(el['price_list_id'])
                el['data'] = {'status': 'fresh' if price_list else 'unavailable', 'revision': price_revision(price_list) if price_list else None, 'total': len(price_list['items']) if price_list else 0}
                el['rows'] = min(el['rows'], preference.items_per_page if preference else 5)
                el['fetch_path'] = f'/api/v1/devices/{device.external_id}/price-lists/{el["price_list_id"]}/page/'
            if el['kind'] == 'message':
                message = max(content_data['messages'], key=lambda row: row['id'], default=None)
                el['data'] = {'value': message['message'] if message else None, 'status': 'fresh' if message else 'unavailable'}
                el['expires_at'] = message['expires_at'].isoformat() if message else None
            if el['kind'] == 'weather':
                from core.studio_operations import weather_value
                el['data'] = weather_value(preference.city if preference else None)
                el['expires_at'] = el['data'].get('expires_at')
                el['updated_at'] = el['data'].get('updated_at')
        doc.update({'version_id': version.pk, 'number': version.number, 'template_key': version.template.key})
        origins.append({'template': version.template.key, 'version_id': version.pk, 'scope': assignment.scope, 'assignment_id': assignment.pk})
        if doc['kind'] == 'page':
            pages.append(doc)
        else:
            special[doc['kind']] = doc
    controls = {'page_seconds': 30, 'item_seconds': 10, 'items_per_page': 5, 'resume_seconds': 30, 'automatic': True, 'touch_short': 'next_batch', 'touch_long': 'next_page'}
    if preference:
        controls.update({k: getattr(preference, k) for k in controls})
    manifest = {'schema': 'gadget.display.v1', 'pages': pages, 'special': special, 'controls': controls, 'origins': origins,
                'offline_policy': 'show_cached_only_until_expiry_then_fallback', 'timezone': platform_settings().timezone, 'city': str(preference.city) if preference and preference.city else None}
    # Configuration revision excludes changing market samples; price releases are tracked separately.
    revision = digest({'origins': origins, 'controls': controls, 'city': manifest['city'], 'charts': preference.charts if preference else {}})
    manifest['assets'] = [{'id': asset.pk, 'kind': asset.kind, 'sha256': asset.sha256, 'animated': asset.animated, 'fetch_path': f'/api/v1/devices/{device.external_id}/display/assets/{asset.pk}/'} for asset in DisplayAsset.objects.filter(pk__in=manifest_assets(manifest))]
    manifest['revision'] = revision
    manifest['server_time'] = timezone.now().isoformat()
    return manifest


def manifest_assets(manifest):
    ids = set()
    def collect(doc):
        if doc.get('background_asset'):
            ids.add(doc['background_asset'])
        for el in doc.get('elements', []):
            ids.update(el[k] for k in ['image_asset', 'font_asset'] if el.get(k))
            if el.get('fallback'):
                collect(el['fallback'])
    for doc in manifest['pages'] + list(manifest['special'].values()):
        collect(doc)
    return ids


def offer_manifest(device, manifest):
    # Persist identifiers only, never market values; receipt history remains an audit trail.
    DeviceReceipt.objects.get_or_create(device=device, revision=manifest['revision'], defaults={'manifest': {'origins': manifest['origins']}})
