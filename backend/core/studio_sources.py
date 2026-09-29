import json
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from core.models import MarketSample
from core.price_versions import decimal_price
from core.source_engine import path_value


def scalar_paths(raw):
    obj = json.loads(raw)
    result = []
    def walk(value, path='', depth=0):
        if depth > 12 or len(result) >= 300:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if '.' not in key:
                    walk(child, f'{path}.{key}' if path else key, depth+1)
        elif isinstance(value, list):
            for index, child in enumerate(value[:10]):
                walk(child, f'{path}.{index}' if path else str(index), depth+1)
        else:
            # Only paths, types, and redacted examples: sample API secrets are never echoed.
            result.append({'path': path, 'type': type(value).__name__})
    walk(obj)
    return result


def extract_fields(source, raw):
    definitions = list(source.data_fields.all())
    if not definitions:
        return {}
    data = json.loads(raw)
    output = {}
    for field in definitions[:40]:
        try:
            value = path_value(data, field.path)
            if field.numeric:
                value = format(decimal_price(value, allow_negative=True), 'f')
            entry = {'value': value, 'unit': field.unit, 'label': field.label}
            if field.timestamp_path:
                raw_time = path_value(data, field.timestamp_path)
                moment = parse_datetime(raw_time)
                if moment is None:
                    moment = datetime.fromtimestamp(float(raw_time), tz=timezone.get_default_timezone())
                if timezone.is_naive(moment) or moment > timezone.now():
                    raise ValueError
                entry['observed_at'] = moment.isoformat()
            if all([field.open_path, field.high_path, field.low_path, field.close_path]):
                ohlc = {name: format(decimal_price(path_value(data, getattr(field, name+'_path'))), 'f') for name in ['open', 'high', 'low', 'close']}
                if Decimal(ohlc['low']) > min(Decimal(ohlc['open']), Decimal(ohlc['close'])) or Decimal(ohlc['high']) < max(Decimal(ohlc['open']), Decimal(ohlc['close'])):
                    raise ValueError
                entry['ohlc'] = ohlc
            output[field.key] = entry
        except (KeyError, IndexError, TypeError, ValueError, ValidationError, OverflowError):
            output[field.key] = {'value': None, 'unit': field.unit, 'label': field.label, 'status': 'invalid'}
    return output


def record_fields(source, content, observed_at):
    fields = content.get('fields', {})
    for field in source.data_fields.filter(keep_history=True, numeric=True):
        entry = fields.get(field.key, {})
        if entry.get('value') is None:
            continue
        moment = parse_datetime(entry['observed_at']) if entry.get('observed_at') else observed_at
        MarketSample.objects.update_or_create(field=field, observed_at=moment, defaults={'value': decimal_price(entry['value'], allow_negative=True), 'ohlc': entry.get('ohlc', {}), 'origin': 'provider' if entry.get('ohlc') else 'sample'})
