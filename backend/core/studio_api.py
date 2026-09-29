from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.views import _authenticated_device
from core.models import DeviceReceipt, DisplayAsset
from core.studio_contract import build_manifest, offer_manifest, manifest_assets, allowed_data, price_revision


@api_view(['GET'])
def display(request, external_id):
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    manifest = build_manifest(device)
    offer_manifest(device, manifest)
    response = Response(manifest)
    response['Cache-Control'] = 'no-store'
    return response


@api_view(['POST'])
def receipt(request, external_id):
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    data = request.data
    if not isinstance(data, dict) or data.get('state') not in ['received', 'applied']:
        return Response({'detail': 'Invalid receipt'}, status=400)
    if not isinstance(data.get('revision'), str) or len(data['revision']) != 64:
        return Response({'detail': 'Invalid revision'}, status=400)
    record = DeviceReceipt.objects.filter(device=device, revision=data.get('revision')).first()
    if record is None:
        return Response({'detail': 'Version has not been offered to this device'}, status=409)
    fields = {}
    if not record.received_at:
        fields['received_at'] = timezone.now()
    if data['state'] == 'applied' and not record.applied_at:
        fields['applied_at'] = timezone.now()
    DeviceReceipt.objects.filter(pk=record.pk).update(**fields)
    return Response({'acknowledged': True})


def price_page_data(device, pk, revision, offset, limit):
    _, _, lists = allowed_data(device)
    row = lists.get(pk)
    if row is None:
        return {'detail': 'Not found'}, 404
    # Includes legacy items in digest: old endpoints may change rows without bumping revision.
    current = price_revision(row)
    if revision and revision != current:
        return {'detail': 'Price list changed', 'revision': current}, 409
    if not 0 <= offset or not 1 <= limit <= 20:
        return {'detail': 'Invalid pagination'}, 400
    result = {'id': pk, 'revision': current, 'offset': offset, 'total': len(row['items']), 'items': row['items'][offset:offset+limit], 'next_offset': offset+limit if offset+limit < len(row['items']) else None}
    return result, 200


@api_view(['GET'])
def price_page(request, external_id, pk):
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    try:
        result, status = price_page_data(device, pk, request.GET.get('revision', ''), int(request.GET.get('offset', 0)), int(request.GET.get('limit', 5)))
    except ValueError:
        return Response({'detail': 'Invalid pagination'}, status=400)
    if status == 200:
        receipt_revision = 'price:' + str(pk) + ':' + result['revision']
        import hashlib
        receipt_revision = hashlib.sha256(receipt_revision.encode()).hexdigest()
        DeviceReceipt.objects.get_or_create(device=device, revision=receipt_revision, defaults={'manifest': {'price_list': pk, 'price_revision': result['revision']}})
        result['receipt_revision'] = receipt_revision
    response = Response(result, status=status)
    response['Cache-Control'] = 'no-store'
    return response


@api_view(['GET'])
def asset(request, external_id, pk):
    device, error = _authenticated_device(request, external_id)
    if error is not None:
        return error
    if pk not in manifest_assets(build_manifest(device)):
        return HttpResponse(status=404)
    obj = get_object_or_404(DisplayAsset, pk=pk)
    response = FileResponse(obj.file.open('rb'), content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=86400'
    response['ETag'] = obj.sha256
    return response
