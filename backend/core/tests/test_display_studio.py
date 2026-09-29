import io
import json
import zipfile
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template
from django.test import Client
from django.utils import timezone
from core.models import (Company, CompanyMembership, WordPressDevice, DisplayProfile, DisplayTemplate,
    DisplayAssignment, DisplayPreference, DisplayAsset, SourceField, ExternalDataSource,
    SourceSelection, PriceList, ProductSample, PriceRelease, DeviceReceipt, OperationJob,
    OperationsPolicy, MarketSample, OperationalAlert)
from core.studio_contract import validate_document, publish_template, build_manifest, chart_points
from core.price_versions import schedule_release, activate_due_release, current_release, read_xlsx
from core.source_engine import extract, store_value
from core.studio_sources import scalar_paths
from core.studio_operations import schedule_backup, process_jobs, set_alert
from core.device_auth import generate_device_token


@pytest.fixture
def environment():
    owner = get_user_model().objects.create_superuser('studio-owner', password='strong-test-password')
    customer = get_user_model().objects.create_user('studio-customer', password='strong-test-password')
    company = Company.objects.create(name='شرکت آزمایش', slug='studio-company')
    CompanyMembership.objects.create(user=customer, company=company, role='company_admin')
    token, hashed = generate_device_token()
    device = WordPressDevice.objects.create(external_id='studio-device', company=company, assigned_user=customer, plan='pro', provisioning_state='provisioned', device_token_hash=hashed)
    profile = DisplayProfile.objects.create(name='Test TFT', width=480, height=320)
    template = DisplayTemplate.objects.create(name='طرح آزمایش', key='test-display', profile=profile)
    client = Client()
    client.force_login(owner)
    return owner, customer, company, device, token, template, client


def element(**changes):
    return {'id': 'price', 'kind': 'text', 'x': 0, 'y': 0, 'width': 200, 'height': 60, 'text': 'متن فارسی', **changes}


def publish(template, owner, **el):
    template.draft = {'elements': [element(**el)]}
    template.save()
    version = publish_template(template.pk, owner, template.draft_revision)
    DisplayAssignment.objects.create(version=version, scope='global')
    return version


def price_row(code='gold', amount='100', unit='تومان'):
    return {'code': code, 'name': code, 'amount': amount, 'unit': unit, 'valid_until': (timezone.now()+timedelta(days=2)).isoformat()}


@pytest.mark.parametrize('overrides', [{'x': -1}, {'width': 700}, {'height': 0}, {'color': 'url(evil)'}, {'pulse_ms': 1000}, {'glow': 8}, {'font_asset': 99999}])
def test_preflight_rejects_invalid_geometry_assets_and_unsupported_effects(environment, overrides):
    *_, template, _client = environment
    with pytest.raises(ValidationError):
        validate_document(template, {'elements': [element(**overrides)]})


def test_version_snapshot_and_optimistic_draft_lock(environment):
    owner, _, _, _, _, template, client = environment
    version = publish(template, owner)
    template.draft['elements'][0]['text'] = 'جدید'
    template.save()
    version.refresh_from_db()
    assert version.document['elements'][0]['text'] == 'متن فارسی'
    url = f'/panel/studio/{template.pk}/save/'
    response = client.post(url, json.dumps({'revision': 1, 'document': template.draft}), content_type='application/json')
    assert response.status_code == 200
    assert client.post(url, json.dumps({'revision': 1, 'document': template.draft}), content_type='application/json').status_code == 409


def test_assignment_precedence_and_plan_restriction(environment):
    owner, customer, company, device, _, template, _ = environment
    first = publish(template, owner)
    template.draft['elements'][0]['text'] = 'اختصاصی'
    template.save()
    second = publish_template(template.pk, owner, 1)
    DisplayAssignment.objects.create(version=second, scope='company', company=company)
    manifest = build_manifest(device)
    assert manifest['pages'][0]['version_id'] == second.pk
    assert manifest['origins'][0]['scope'] == 'company'
    DisplayAssignment.objects.create(version=first, scope='device', device=device, plan='simple')
    assert build_manifest(device)['pages'][0]['version_id'] == second.pk
    DisplayAssignment.objects.create(version=first, scope='user', user=customer)
    assert build_manifest(device)['pages'][0]['version_id'] == first.pk


def test_source_fields_private_data_not_exposed_to_other_company(environment):
    owner, _, company, device, _, template, _ = environment
    other = Company.objects.create(name='Other', slug='other-studio')
    source = ExternalDataSource.objects.create(name='Private', company=other, source_type='http', value_path='price', display_key='private-price', ttl_seconds=600)
    field = SourceField.objects.create(source=source, key='price', label='Price', path='price', numeric=True, keep_history=True)
    SourceSelection.objects.create(device=device, source=source)
    assert store_value(source, extract(source, '{"price": 100}'))
    publish(template, owner, kind='value', field_id=field.pk)
    el = build_manifest(device)['pages'][0]['elements'][0]
    assert el['data']['value'] is None
    assert el['data']['status'] == 'unavailable'


def test_extract_multiple_values_and_provider_ohlc_updates_same_candle(environment):
    _, _, _, device, _, _, _ = environment
    source = ExternalDataSource.objects.create(name='Market', source_type='http', value_path='quote.price', display_key='market', ttl_seconds=600)
    field = SourceField.objects.create(source=source, key='price', label='Price', path='quote.price', numeric=True, keep_history=True, timestamp_path='at', open_path='o', high_path='h', low_path='l', close_path='c')
    SourceField.objects.create(source=source, key='change', label='Change', path='change', numeric=True)
    stamp = (timezone.now()-timedelta(seconds=10)).isoformat()
    raw = json.dumps({'quote': {'price': 101}, 'change': -2.5, 'at': stamp, 'o': 100, 'h': 105, 'l': 99, 'c': 101})
    content = extract(source, raw)
    assert content['fields']['change']['value'] == '-2.5'
    assert store_value(source, content)
    content['fields']['price']['ohlc']['high'] = '107'
    assert store_value(source, content)
    assert MarketSample.objects.filter(field=field).count() == 1
    assert field.samples.get().ohlc['high'] == '107'
    points = chart_points(field=field, timeframe=300, count=10)
    assert points[0]['origin'] == 'provider'
    assert scalar_paths('{"token":"secret","quote":{"price":12}}') == [{'path': 'token', 'type': 'str'}, {'path': 'quote.price', 'type': 'int'}]


def test_price_release_atomic_activation_history_and_no_duplicate(environment):
    owner, _, company, device, _, _, _ = environment
    price_list = PriceList.objects.create(company=company, name='List')
    price_list.target_devices.add(device)
    release = schedule_release(price_list, [price_row(), price_row('silver', '50')], timezone.now(), owner)
    assert current_release(price_list) is None
    assert activate_due_release(release.pk)
    assert not activate_due_release(release.pk)
    assert price_list.items.count() == 2
    assert ProductSample.objects.filter(release=release).count() == 2
    same = schedule_release(price_list, [price_row(), price_row('silver', '50')], timezone.now(), owner)
    activate_due_release(same.pk)
    assert ProductSample.objects.filter(release=same).count() == 0
    with pytest.raises(ValidationError):
        schedule_release(price_list, [price_row(), price_row()], timezone.now(), owner)
    future = schedule_release(price_list, [price_row(amount='120')], timezone.now()+timedelta(hours=1), owner)
    assert not activate_due_release(future.pk)
    assert current_release(price_list).pk == same.pk


def test_device_pagination_revision_scope_and_ack(environment):
    owner, _, company, device, token, template, client = environment
    price_list = PriceList.objects.create(company=company, name='List')
    price_list.target_devices.add(device)
    release = schedule_release(price_list, [price_row(str(i), str(i+10)) for i in range(12)], timezone.now(), owner)
    activate_due_release(release.pk)
    publish(template, owner, kind='prices', price_list_id=price_list.pk, rows=5)
    client.logout()
    headers = {'HTTP_X_DEVICE_TOKEN': token}
    url = f'/api/v1/devices/{device.external_id}/price-lists/{price_list.pk}/page/'
    assert client.get(url).status_code == 401
    result = client.get(url, {'limit': 5, 'offset': 5}, **headers).json()
    assert len(result['items']) == 5 and result['items'][0]['code'] == '5'
    assert client.get(url, {'revision': 'old'}, **headers).status_code == 409
    assert client.get(url, {'limit': 1000}, **headers).status_code == 400
    assert client.get(url.replace(f'/{price_list.pk}/page', '/9999/page'), **headers).status_code == 404
    ack = f'/api/v1/devices/{device.external_id}/display/receipt/'
    assert client.post(ack, {'revision': '0'*64, 'state': 'applied'}, **headers).status_code == 409
    assert client.post(ack, {'revision': result['receipt_revision'], 'state': 'applied'}, **headers).status_code == 200
    assert DeviceReceipt.objects.get(revision=result['receipt_revision']).applied_at
    manifest = client.get(f'/api/v1/devices/{device.external_id}/display/', **headers).json()
    assert client.post(ack, {'revision': manifest['revision'], 'state': 'received'}, **headers).status_code == 200


def xlsx(formula=False):
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>code</t></is></c><c r="B1" t="inlineStr"><is><t>name</t></is></c><c r="C1" t="inlineStr"><is><t>amount</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>gold</t></is></c><c r="B2" t="inlineStr"><is><t>طلا</t></is></c><c r="C2">'+('<f>1+2</f>' if formula else '')+'<v>100</v></c></row></sheetData></worksheet>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('xl/worksheets/sheet1.xml', xml)
    return SimpleUploadedFile('prices.xlsx', output.getvalue())


def test_excel_parse_formula_rejection_and_import_idempotency(environment):
    owner, _, company, _, _, _, client = environment
    columns, rows = read_xlsx(xlsx())
    assert columns == ['code', 'name', 'amount'] and rows[0] == ['gold', 'طلا', '100']
    with pytest.raises(ValidationError):
        read_xlsx(xlsx(formula=True))
    price_list = PriceList.objects.create(company=company, name='List')
    response = client.post(f'/panel/prices/{price_list.pk}/import/', {'file': xlsx()})
    assert response.status_code == 302
    url = response.url
    payload = {'code': '0', 'name': '1', 'amount': '2', 'unit': 'تومان', 'scheduled_at': timezone.now().isoformat(), 'valid_until': (timezone.now()+timedelta(days=1)).isoformat(), 'confirm': 'on'}
    assert client.post(url, payload).status_code == 302
    assert PriceRelease.objects.filter(price_list=price_list).count() == 1
    assert client.post(url, payload).status_code == 404


def test_ops_jobs_retry_without_secrets_and_scheduling(environment):
    OperationsPolicy.objects.create(backup_enabled=True, backup_hours=24)
    schedule_backup()
    schedule_backup()
    assert OperationJob.objects.count() == 1
    with patch('core.studio_operations.make_backup', side_effect=RuntimeError('sensitive password')):
        process_jobs()
    job = OperationJob.objects.get()
    assert job.status == 'pending' and 'sensitive' not in job.result
    OperationJob.objects.filter(pk=job.pk).update(next_attempt=timezone.now())
    with patch('core.studio_operations.make_backup', return_value='backup.tar.gz'):
        process_jobs()
    job.refresh_from_db()
    assert job.status == 'done'


def test_alert_transitions_deduplicate_jobs(environment):
    OperationsPolicy.objects.create(sms_enabled=True)
    set_alert('mqtt', True, 'down')
    set_alert('mqtt', True, 'down again')
    assert OperationJob.objects.filter(kind='sms').count() == 1
    set_alert('mqtt', False, '')
    assert OperationJob.objects.filter(kind='sms').count() == 2
    assert not OperationalAlert.objects.get(service='mqtt').active


def test_chart_preferences_stay_within_published_limits(environment):
    owner, customer, _, device, _, template, client = environment
    source = ExternalDataSource.objects.create(name='Market', source_type='http', value_path='p', display_key='p')
    field = SourceField.objects.create(source=source, key='p', label='p', path='p', numeric=True, keep_history=True)
    publish(template, owner, kind='chart', field_id=field.pk, customizable=True, max_points=60, timeframes=[300], allowed_types=['line'])
    client.force_login(customer)
    key = f'{template.key}:price'
    payload = {'key': key, 'chart_type': 'candle', 'timeframe': 300, 'max_points': 30, 'up_color': '#00ff00', 'down_color': '#ff0000'}
    url = f'/panel/devices/{device.pk}/chart-preferences/'
    assert client.post(url, payload).status_code == 400
    payload['chart_type'] = 'line'
    assert client.post(url, payload).status_code == 302
    payload['max_points'] = 50
    assert client.post(url, payload).status_code == 302
    assert DisplayPreference.objects.get(device=device).charts[key]['max_points'] == 50


def test_customers_cannot_access_studio_or_other_device(environment):
    _, customer, _, _, _, _, client = environment
    client.force_login(customer)
    assert client.get('/panel/studio/').status_code == 403
    assert client.get('/panel/operations/').status_code == 403
    assert client.get('/panel/devices/99999/simulator/').status_code == 404
    assert client.post('/panel/operations/backup/').status_code == 403


def test_owner_studio_pages_render_and_templates_compile(environment):
    from django.conf import settings
    _, _, _, device, _, template, client = environment
    urls = ['/panel/studio/', '/panel/studio/profiles/new/', '/panel/studio/new/', f'/panel/studio/{template.pk}/', '/panel/studio/assignments/new/', '/panel/studio/assets/new/', '/panel/studio/cities/new/', '/panel/operations/', f'/panel/devices/{device.pk}/simulator/', f'/panel/devices/{device.pk}/display-preferences/', f'/panel/devices/{device.pk}/receipts/']
    for url in urls:
        assert client.get(url).status_code == 200, url
    for file in (settings.BASE_DIR/'core/templates/core/studio').glob('*.html'):
        get_template('core/studio/'+file.name)


def test_image_upload_normalizes_untrusted_extension(environment):
    from PIL import Image
    _, _, _, _, _, _, client = environment
    raw = io.BytesIO()
    Image.new('RGB', (10, 10)).save(raw, format='PNG')
    response = client.post('/panel/studio/assets/new/', {'name': 'Safe asset', 'kind': 'image', 'file': SimpleUploadedFile('evil.html', raw.getvalue(), content_type='text/html')})
    assert response.status_code == 302
    assert DisplayAsset.objects.get().file.name.endswith('.png')


def test_legacy_price_revision_matches_manifest_and_http(environment):
    from core.models import PriceItem
    from core.studio_api import price_page_data
    owner, _, company, device, _, template, _ = environment
    prices = PriceList.objects.create(company=company, name='Legacy')
    prices.target_devices.add(device)
    PriceItem.objects.create(price_list=prices, code='one', name='One', amount=100, unit='تومان', valid_until=timezone.now()+timedelta(days=1))
    publish(template, owner, kind='prices', price_list_id=prices.pk)
    revision = build_manifest(device)['pages'][0]['elements'][0]['data']['revision']
    result, status = price_page_data(device, prices.pk, revision, 0, 5)
    assert status == 200 and result['revision'] == revision


def test_history_stops_at_unit_change(environment):
    from core.models import PriceItem
    _, _, company, _, _, _, _ = environment
    prices = PriceList.objects.create(company=company, name='Units')
    item = PriceItem.objects.create(price_list=prices, code='x', name='X', amount=100, unit='تومان', valid_until=timezone.now()+timedelta(days=1))
    ProductSample.objects.filter(item=item).delete()
    now = timezone.now()
    for n, unit, amount in [(3, 'تومان', 100), (2, 'ریال', 1000), (1, 'تومان', 120)]:
        ProductSample.objects.create(item=item, observed_at=now-timedelta(minutes=n), amount=amount, unit=unit)
    points = chart_points(product=item, timeframe=60, count=10)
    assert len(points) == 1 and points[0]['close'] == '120.00000000'


def test_preference_change_bumps_config_version(environment):
    from core.config_sync import refresh_device_config
    _, _, _, device, _, _, _ = environment
    refresh_device_config(device.pk)
    device.refresh_from_db()
    previous = device.ui_version
    DisplayPreference.objects.create(device=device, page_seconds=90)
    refresh_device_config(device.pk)
    device.refresh_from_db()
    assert device.ui_version == previous+1


def test_non_http_field_editor_is_bad_request(environment):
    _, _, _, _, _, _, client = environment
    source = ExternalDataSource.objects.create(name='Manual', source_type='manual', display_key='manual-test')
    assert client.get(f'/panel/data-sources/{source.pk}/fields/').status_code == 400


def test_slow_backups_not_run_in_scheduling_cycle(environment):
    from core.studio_operations import tick
    OperationJob.objects.create(kind='backup', key='backup-test', next_attempt=timezone.now())
    with patch('core.studio_operations.make_backup') as backup:
        tick()
    backup.assert_not_called()
    assert OperationJob.objects.get(key='backup-test').status == 'pending'


def test_manual_price_draft_is_not_live_or_charted_until_publication(environment):
    owner, _, company, device, _, _, client = environment
    prices = PriceList.objects.create(company=company, name='Draft test')
    prices.target_devices.add(device)
    first = schedule_release(prices, [price_row()], timezone.now(), owner)
    activate_due_release(first.pk)
    item = prices.items.get()
    item.amount = 150
    item.save()
    assert item.history.count() == 1
    assert current_release(prices).items[0]['amount'] == '100'
    response = client.post(f'/panel/prices/{prices.pk}/releases/', {'scheduled_at': timezone.now().isoformat(), 'confirm': 'on'})
    assert response.status_code == 302
    second = prices.releases.get(number=2)
    assert second.items[0]['amount'] == '150.00000000'
    activate_due_release(second.pk)
    assert item.history.count() == 2


def test_weather_cache_key_changes_with_coordinates_and_unit(environment):
    from core.models import City
    from core.studio_operations import weather_key
    city = City.objects.create(name='Test city', latitude=35, longitude=51)
    config = OperationsPolicy.objects.create(pk=1)
    key = weather_key(city, config)
    city.latitude = 36
    assert key != weather_key(city, config)
    city.latitude = 35
    config.weather_unit = 'F'
    assert key != weather_key(city, config)


def test_old_provider_timestamp_is_not_presented_as_fresh(environment):
    owner, _, _, device, _, template, _ = environment
    source = ExternalDataSource.objects.create(name='Stale provider', source_type='http', value_path='price', display_key='stale-provider', ttl_seconds=60)
    field = SourceField.objects.create(source=source, key='price', label='Price', path='price', numeric=True, timestamp_path='time')
    SourceSelection.objects.create(device=device, source=source)
    store_value(source, extract(source, json.dumps({'price': 10, 'time': (timezone.now()-timedelta(hours=1)).isoformat()})))
    publish(template, owner, kind='value', field_id=field.pk)
    assert build_manifest(device)['pages'][0]['elements'][0]['data']['status'] == 'unavailable'


def test_invalid_draft_body_and_missing_template(environment):
    _, _, _, _, _, template, client = environment
    assert client.post(f'/panel/studio/{template.pk}/save/', '[]', content_type='application/json').status_code == 400
    assert client.post('/panel/studio/999999/publish/', {'revision': 1}).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_real_sqlite_backup_is_private_restorable_and_idempotent(tmp_path, settings):
    import sqlite3
    import tarfile
    from core.studio_operations import make_backup
    from django.db import connection
    if connection.vendor != 'sqlite':
        pytest.skip('SQLite-specific local restore check; PostgreSQL is covered by deployment restore acceptance.')
    settings.GADGET_BACKUP_DIR = tmp_path/'backups'
    settings.MEDIA_ROOT = tmp_path/'media'
    settings.MEDIA_ROOT.mkdir()
    (settings.MEDIA_ROOT/'logo.txt').write_text('retained media')
    user = get_user_model().objects.create_user('backup-probe')
    job = OperationJob.objects.create(kind='backup', key='restore-test', next_attempt=timezone.now())
    name = make_backup(job)
    file = settings.GADGET_BACKUP_DIR/name
    assert file.stat().st_mode & 0o777 == 0o600
    assert make_backup(job) == name
    with tarfile.open(file) as archive:
        assert {'database.dump', 'recovery-settings.json', 'media/logo.txt'} <= set(archive.getnames())
        restored = tmp_path/'restored.sqlite3'
        restored.write_bytes(archive.extractfile('database.dump').read())
    with sqlite3.connect(restored) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT username FROM auth_user WHERE id=?', (user.pk,)).fetchone()[0] == 'backup-probe'


def test_message_element_uses_only_targeted_unexpired_campaign(environment):
    from core.models import MessageCampaign
    owner, _, company, device, _, template, _ = environment
    message = MessageCampaign.objects.create(company=company, name='Targeted', message='پیام نماینده', status='sent', expires_at=timezone.now()+timedelta(hours=1))
    message.target_devices.add(device)
    MessageCampaign.objects.create(company=company, name='Not targeted', message='نباید دیده شود', status='sent', expires_at=timezone.now()+timedelta(hours=1))
    publish(template, owner, kind='message')
    manifest = build_manifest(device)
    assert manifest['pages'][0]['elements'][0]['data']['value'] == 'پیام نماینده'
    message.expires_at = timezone.now()-timedelta(seconds=1)
    message.save()
    assert build_manifest(device)['pages'][0]['elements'][0]['data']['status'] == 'unavailable'


def test_owner_can_retry_failed_operation_without_changing_settings(environment):
    _, customer, _, _, _, _, client = environment
    job = OperationJob.objects.create(kind='backup', key='failed-test', status='failed', attempts=5, next_attempt=timezone.now())
    assert client.post('/panel/operations/', {'retry_job': str(job.pk)}).status_code == 302
    job.refresh_from_db()
    assert job.status == 'pending' and job.attempts == 0
    client.force_login(customer)
    assert client.post('/panel/operations/', {'retry_job': str(job.pk)}).status_code == 403
