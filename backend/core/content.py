from django.utils import timezone
from django.db.models import Q
from core.access import source_allowed, rule_for, ancestor_company_ids
from core.models import SourceSelection, PriceList, PriceItem, MessageCampaign
from core.source_engine import read_value


def device_content(device):
    rule = rule_for(device.normalized_plan)
    sources = []
    custom_count = telegram_count = 0
    for selection in SourceSelection.objects.filter(device=device, enabled=True).select_related("source", "source__created_by"):
        source = selection.source
        if not source_allowed(device, source):
            continue
        if source.company_id:
            if not rule.can_add_sources:
                continue
            if source.source_type == "telegram":
                telegram_count += 1
                if telegram_count > rule.max_telegram_sources:
                    continue
            else:
                custom_count += 1
                if custom_count > rule.max_sources:
                    continue
        value = read_value(source)
        sources.append({"id": source.pk, "key": source.display_key, "name": source.name, "category": source.category, "status": "fresh" if value else "waiting", "data": value})
    now = timezone.now()
    lists = []
    for price_list in PriceList.objects.filter(target_devices=device, is_active=True, company_id__in=ancestor_company_ids(device.company_id)):
        items = []
        for item in price_list.items.all():
            valid = item.valid_until > now and item.amount is not None
            items.append({"code": item.code, "name": item.name, "amount": format(item.amount.normalize(), "f") if valid else None, "unit": item.unit, "valid_until": item.valid_until.isoformat(), "status": "fresh" if valid else "expired"})
        lists.append({"id": price_list.pk, "name": price_list.name, "revision": price_list.revision, "items": items})
    campaigns = MessageCampaign.objects.filter(target_devices=device, company_id__in=ancestor_company_ids(device.company_id), expires_at__gt=now).filter(Q(status="sent") | Q(deliveries__device=device, deliveries__delivered_at__isnull=False)).distinct().values("id", "name", "message", "expires_at")
    return {"server_time": now.isoformat(), "sources": sources, "price_lists": lists, "messages": list(campaigns), "poll_after_seconds": rule.min_refresh_seconds, "live_updates": getattr(getattr(device, "preferences", None), "live_updates", True)}


def purge_expired_content():
    from core.runtime import platform_settings
    if not platform_settings().cleanup_enabled:
        return 0
    now = timezone.now()
    # Keep product identities, discard expired price values and message bodies.
    prices = PriceItem.objects.filter(valid_until__lte=now, amount__isnull=False, disposable=True).update(amount=None)
    messages = MessageCampaign.objects.filter(expires_at__lte=now, disposable=True).exclude(message="").update(message="")
    return prices + messages
