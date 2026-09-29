import json
import mimetypes
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from core.access import is_platform_owner, is_platform_user, visible_devices, visible_sources, managed_company_ids
from core.console_views import owner_only, audit, form_page, manage_company
from core.models import (DisplayProfile, DisplayAsset, DisplayTemplate, DisplayVersion, DisplayAssignment,
                         City, DisplayPreference, SourceField, PriceList, PriceItem, ImportBatch,
                         DeviceReceipt, OperationsPolicy, OperationJob, OperationalAlert)
from core.studio_forms import (ProfileForm, AssetForm, TemplateForm, AssignmentForm, CityForm,
                              DisplayPreferenceForm, SourceFieldForm, ExcelForm, ImportMappingForm, OperationsForm, PublishPricesForm)
from core.studio_contract import (validate_document, publish_template, build_manifest, manifest_assets,
                                 assignments_for, chart_override)
from core.price_versions import read_xlsx, schedule_release


@owner_only
def home(request):
    return render(request, 'core/studio/home.html', {'templates': DisplayTemplate.objects.select_related('profile'),
        'profiles': DisplayProfile.objects.all(), 'assignments': DisplayAssignment.objects.select_related('version__template', 'company', 'user', 'device'),
        'assets': DisplayAsset.objects.all(), 'cities': City.objects.all()})


@owner_only
def profile_editor(request, pk=None):
    obj = get_object_or_404(DisplayProfile, pk=pk) if pk else None
    form = ProfileForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        audit(request, 'display.profile', obj)
        return redirect('panel-studio')
    return form_page(request, form, 'پروفایل نمایشگر', 'panel-studio', note='ابعاد باید با نمایشگر واقعی برابر باشند. قابلیت‌های جلوه فقط پس از تأیید Firmware فعال شوند.')


@owner_only
def city_editor(request, pk=None):
    obj = get_object_or_404(City, pk=pk) if pk else None
    form = CityForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('panel-studio')
    return form_page(request, form, 'شهر قابل انتخاب', 'panel-studio')


@owner_only
def asset_upload(request):
    form = AssetForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        audit(request, 'display.asset.upload', obj)
        return redirect('panel-studio')
    return form_page(request, form, 'بارگذاری تصویر یا فونت', 'panel-studio', note='طرح و لوگوی خودتان را وارد کنید. قالب نمونه خودکار ساخته نمی‌شود.')


@login_required
def asset_preview(request, pk):
    obj = get_object_or_404(DisplayAsset, pk=pk)
    from core.staff_access import has_permission
    if not has_permission(request.user, 'templates.view'):
        device = get_object_or_404(visible_devices(request.user), pk=request.GET.get('device'))
        if pk not in manifest_assets(build_manifest(device)):
            raise PermissionDenied
    content_type = 'font/ttf' if obj.kind == 'font' else mimetypes.guess_type(obj.file.name)[0] or 'application/octet-stream'
    response = FileResponse(obj.file.open('rb'), content_type=content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=3600'
    return response


@owner_only
def template_create(request):
    form = TemplateForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        audit(request, 'display.template.create', obj)
        return redirect('panel-studio-editor', pk=obj.pk)
    return form_page(request, form, 'قالب خالی جدید', 'panel-studio')


def catalog():
    return {'fields': list(SourceField.objects.select_related('source').values('id', 'label', 'source__name', 'unit', 'numeric', 'keep_history')),
            'products': list(PriceItem.objects.values('id', 'name', 'code', 'price_list__name', 'unit')),
            'lists': list(PriceList.objects.values('id', 'name')),
            'assets': list(DisplayAsset.objects.values('id', 'name', 'kind')),
            'fallbacks': [{'id': v.pk, 'name': str(v)} for v in DisplayVersion.objects.filter(template__kind='fallback').select_related('template')]}


@owner_only
def editor(request, pk):
    obj = get_object_or_404(DisplayTemplate.objects.select_related('profile'), pk=pk)
    data = {'document': obj.draft or {'background': '#233b55', 'elements': []}, 'revision': obj.draft_revision,
            'width': obj.profile.width, 'height': obj.profile.height, 'catalog': catalog(), 'template_id': obj.pk,
            'save_url': reverse('panel-studio-save', args=[pk]), 'publish_url': reverse('panel-studio-publish', args=[pk])}
    return render(request, 'core/studio/editor.html', {'template': obj, 'studio_data': data, 'versions': obj.versions.order_by('-number')})


@owner_only
@require_POST
def save_draft(request, pk):
    if len(request.body) > 160*1024:
        return JsonResponse({'error': 'طرح بیش از حد بزرگ است.'}, status=400)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        with transaction.atomic():
            obj = get_object_or_404(DisplayTemplate.objects.select_for_update().select_related('profile'), pk=pk)
            if data.get('revision') != obj.draft_revision:
                return JsonResponse({'error': 'نسخه تغییر کرده است؛ صفحه را دوباره باز کنید.'}, status=409)
            document = validate_document(obj, data.get('document'))
            obj.draft = document
            obj.draft_revision += 1
            obj.save(update_fields=['draft', 'draft_revision', 'updated_at'])
            audit(request, 'display.draft.save', obj)
        return JsonResponse({'revision': obj.draft_revision, 'document': document})
    except (ValueError, TypeError, ValidationError) as exc:
        return JsonResponse({'error': '؛ '.join(exc.messages) if isinstance(exc, ValidationError) else 'درخواست نامعتبر است.'}, status=400)


@owner_only
@require_POST
def publish(request, pk):
    get_object_or_404(DisplayTemplate, pk=pk)
    try:
        expected = int(request.POST.get('revision', 0))
        version = publish_template(pk, request.user, expected)
        audit(request, 'display.publish', version)
        return JsonResponse({'version_id': version.pk, 'number': version.number})
    except (ValueError, ValidationError) as exc:
        return JsonResponse({'error': '؛ '.join(exc.messages) if isinstance(exc, ValidationError) else 'نسخه نامعتبر'}, status=400)


@owner_only
def assignment_editor(request, pk=None):
    obj = get_object_or_404(DisplayAssignment, pk=pk) if pk else None
    form = AssignmentForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        audit(request, 'display.assignment', obj.pk)
        from core.config_sync import refresh_all_device_configs
        refresh_all_device_configs()
        return redirect('panel-studio')
    return form_page(request, form, 'مخاطب و نسخه صفحه', 'panel-studio', note='تقدم برای یک شناسه قالب: دستگاه، کاربر، نزدیک‌ترین شرکت، پلن، عمومی. محدودیت پلن در همه سطوح رعایت می‌شود.')


@login_required
def simulator(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    return render(request, 'core/studio/simulator.html', {'device': device,
        'simulator_data': {'url': reverse('panel-studio-manifest', args=[pk]), 'asset_prefix': '/panel/studio/assets/', 'device_id': pk, 'price_url': reverse('panel-studio-price-page', args=[pk, 0]).replace('/0/', '/LIST/')}})


@login_required
def simulator_manifest(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    response = JsonResponse(build_manifest(device))
    response['Cache-Control'] = 'no-store'
    return response


@login_required
def simulator_prices(request, pk, list_pk):
    from core.studio_api import price_page_data
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    try:
        data, status = price_page_data(device, list_pk, request.GET.get('revision', ''), int(request.GET.get('offset', 0)), int(request.GET.get('limit', 5)))
    except ValueError:
        return JsonResponse({'detail': 'Invalid pagination'}, status=400)
    return JsonResponse(data, status=status)


@login_required
def preferences(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    obj = DisplayPreference.objects.filter(device=device).first() or DisplayPreference(device=device)
    form = DisplayPreferenceForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        from core.config_sync import refresh_device_config
        refresh_device_config(device.pk)
        audit(request, 'display.preference', device)
        return redirect('panel-studio-preferences', pk=pk)
    manifest = build_manifest(device)
    charts = [el for page in manifest['pages'] for el in page['elements'] if el['kind'] == 'chart' and el.get('customizable')]
    return render(request, 'core/studio/preferences.html', {'form': form, 'device': device, 'charts': charts})


@login_required
@require_POST
def chart_preferences(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    manifest = build_manifest(device)
    key = request.POST.get('key')
    element = next((el for page in manifest['pages'] for el in page['elements'] if el.get('preference_key') == key and el['kind'] == 'chart' and el.get('customizable')), None)
    if element is None:
        raise PermissionDenied
    try:
        override = {'chart_type': request.POST['chart_type'], 'timeframe': int(request.POST['timeframe']), 'max_points': int(request.POST['max_points']), 'up_color': request.POST['up_color'], 'down_color': request.POST['down_color']}
    except (KeyError, ValueError):
        return HttpResponse(status=400)
    # Compare against the published element, not a previously narrowed override.
    original = next(el for a in assignments_for(device) for el in a.version.document['elements'] if f'{a.version.template.key}:{el["id"]}' == key)
    candidate = DisplayPreference(charts={key: override})
    validated = chart_override(original, candidate, key)
    if any(validated.get(k) != v for k, v in override.items()):
        return HttpResponse('تنظیم نمودار خارج از محدوده مجاز است.', status=400)
    with transaction.atomic():
        from core.models import WordPressDevice
        WordPressDevice.objects.select_for_update().get(pk=device.pk)
        obj, _ = DisplayPreference.objects.get_or_create(device=device)
        obj.charts = {**obj.charts, key: override}
        obj.save()
    from core.config_sync import refresh_device_config
    refresh_device_config(device.pk)
    return redirect('panel-studio-preferences', pk=pk)


def editable_source(request, pk):
    obj = get_object_or_404(visible_sources(request.user), pk=pk)
    if not is_platform_user(request.user) and not (obj.created_by_id == request.user.pk or obj.company_id in managed_company_ids(request.user)):
        raise PermissionDenied
    if obj.source_type != 'http':
        from django.core.exceptions import BadRequest
        raise BadRequest('فیلدهای چندمقداری برای JSON API هستند.')
    return obj


@login_required
def source_fields(request, pk):
    obj = editable_source(request, pk)
    return render(request, 'core/studio/source_fields.html', {'source': obj, 'fields': obj.data_fields.all()})


@login_required
def field_editor(request, pk, field_pk=None):
    source = editable_source(request, pk)
    obj = get_object_or_404(SourceField, source=source, pk=field_pk) if field_pk else SourceField(source=source)
    if not field_pk and source.data_fields.count() >= 40:
        return HttpResponse('حداکثر ۴۰ فیلد برای هر منبع.', status=400)
    form = SourceFieldForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        from core.models import ExternalDataSource
        ExternalDataSource.objects.filter(pk=source.pk).update(updated_at=timezone.now())
        audit(request, 'source.field.save', obj)
        return redirect('panel-source-fields', pk=pk)
    return render(request, 'core/studio/field_editor.html', {'form': form, 'source': source})


@login_required
@require_POST
def discover_fields(request, pk):
    from core.source_engine import fetch_source_body
    from core.studio_sources import scalar_paths
    source = editable_source(request, pk)
    try:
        # Only path names returned. Values, credentials and raw response are not logged or persisted.
        raw = fetch_source_body(source.endpoint_url, source.credential_reference, source.company_id)
        return JsonResponse({'paths': scalar_paths(raw)})
    except Exception:
        return JsonResponse({'error': 'دریافت نمونه ناموفق؛ اتصال و آدرس منبع را بررسی کنید.'}, status=400)


def editable_list(request, pk):
    obj = get_object_or_404(PriceList.objects.filter(company_id__in=managed_company_ids(request.user)), pk=pk)
    manage_company(request, obj.company)
    return obj


@login_required
def excel_upload(request, pk):
    price_list = editable_list(request, pk)
    form = ExcelForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            columns, rows = read_xlsx(form.cleaned_data['file'])
            batch = ImportBatch.objects.create(owner=request.user, price_list=price_list, columns=columns, rows=rows, expires_at=timezone.now()+timedelta(minutes=30))
            return redirect('panel-price-import-map', pk=pk, batch_id=batch.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return form_page(request, form, 'ورود Excel و انتشار قیمت', 'panel-price-list', note='یک شیت، سطر اول عنوان ستون‌ها؛ مقادیر نهایی بدون فرمول. هیچ قیمتی تا تأیید نگاشت و زمان انتشار عوض نمی‌شود.')


@login_required
def import_mapping(request, pk, batch_id):
    price_list = editable_list(request, pk)
    batch = get_object_or_404(ImportBatch, pk=batch_id, owner=request.user, price_list=price_list, expires_at__gt=timezone.now(), consumed_at__isnull=True)
    form = ImportMappingForm(request.POST if request.method == 'POST' else None, columns=batch.columns)
    if request.method == 'POST' and form.is_valid():
        values = form.cleaned_data
        rows = [{key: row[int(values[key])] for key in ['code', 'name', 'amount']} | {'unit': row[int(values['unit_column'])] if values['unit_column'] else values['unit'], 'valid_until': values['valid_until'].isoformat()} for row in batch.rows]
        try:
            with transaction.atomic():
                locked = ImportBatch.objects.select_for_update().get(pk=batch.pk)
                if locked.consumed_at:
                    return HttpResponse('این فایل قبلاً ثبت شده است.', status=409)
                release = schedule_release(price_list, rows, values['scheduled_at'], request.user)
                locked.consumed_at = timezone.now()
                locked.save(update_fields=['consumed_at'])
                audit(request, 'price.release.schedule', release.pk)
            messages.success(request, 'نسخه کامل قیمت ثبت شد؛ سرویس عملیات در زمان تعیین‌شده منتشر می‌کند.')
            return redirect('panel-price-releases', pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'core/studio/import_mapping.html', {'form': form, 'batch': batch, 'rows': batch.rows[:100], 'total': len(batch.rows)})


@login_required
def releases(request, pk):
    obj = editable_list(request, pk)
    form = PublishPricesForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                PriceList.objects.select_for_update().get(pk=pk)
                items = [{'code': i.code, 'name': i.name, 'amount': str(i.amount) if i.amount is not None else '', 'unit': i.unit, 'valid_until': i.valid_until.isoformat()} for i in obj.items.all()]
                release = schedule_release(obj, items, form.cleaned_data['scheduled_at'], request.user)
                audit(request, 'price.release.schedule', release.pk)
            messages.success(request, 'نسخه کامل برای انتشار ثبت شد.')
            return redirect('panel-price-releases', pk=pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'core/studio/releases.html', {'price_list': obj, 'releases': obj.releases.order_by('-number'), 'form': form})


@login_required
def receipts(request, pk):
    device = get_object_or_404(visible_devices(request.user), pk=pk)
    manifest = build_manifest(device)
    return render(request, 'core/studio/receipts.html', {'device': device, 'manifest': manifest, 'receipts': DeviceReceipt.objects.filter(device=device).order_by('-offered_at')[:50]})


@owner_only
def operations(request):
    if not is_platform_owner(request.user):
        raise PermissionDenied
    if request.method == 'POST' and request.POST.get('retry_job'):
        import uuid
        try:
            job_id = uuid.UUID(request.POST['retry_job'])
        except ValueError:
            return HttpResponse(status=400)
        with transaction.atomic():
            job = get_object_or_404(OperationJob.objects.select_for_update(), pk=job_id, status='failed')
            job.status, job.attempts, job.next_attempt, job.result = 'pending', 0, timezone.now(), ''
            job.save(update_fields=['status', 'attempts', 'next_attempt', 'result'])
            audit(request, 'operations.retry', job.pk)
        return redirect('panel-operations')
    obj = OperationsPolicy.objects.get_or_create(pk=1)[0]
    form = OperationsForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if 'backup_hours' in form.changed_data or 'backup_enabled' in form.changed_data:
            OperationsPolicy.objects.filter(pk=1).update(next_backup=None)
        audit(request, 'operations.settings', 'سامانه')
        messages.success(request, 'تنظیمات عملیات ذخیره شد.')
        return redirect('panel-operations')
    return render(request, 'core/studio/operations.html', {'form': form, 'jobs': OperationJob.objects.order_by('-created_at')[:50], 'alerts': OperationalAlert.objects.filter(active=True)})


@owner_only
@require_POST
def backup_now(request):
    if not is_platform_owner(request.user):
        raise PermissionDenied
    from core.studio_operations import enqueue_backup
    job = enqueue_backup(request.user)
    audit(request, 'backup.request', job.pk)
    return redirect('panel-operations')


@owner_only
def backup_download(request, job_id):
    if not is_platform_owner(request.user):
        raise PermissionDenied
    from core.studio_operations import backup_root
    job = get_object_or_404(OperationJob, pk=job_id, kind='backup', status='done')
    file = backup_root()/(str(job.pk)+'.tar.gz')
    if not file.is_file():
        return HttpResponse(status=404)
    audit(request, 'backup.download', job.pk)
    response = FileResponse(file.open('rb'), as_attachment=True, filename=file.name)
    response['Cache-Control'] = 'no-store'
    return response
