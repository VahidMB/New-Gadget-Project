from datetime import timedelta
from django.db import migrations
from django.utils import timezone


def initialize(apps, schema_editor):
    Rule = apps.get_model("core", "PlanRule")
    for name in ("simple", "pro"):
        rule, created = Rule.objects.get_or_create(plan_name=name)
        rule.max_telegram_sources = 2 if name == "pro" else 0
        rule.can_send_messages = name == "pro"
        rule.min_refresh_seconds = 30 if name == "pro" else 300
        if created:
            rule.can_change_theme = True
            rule.can_customize_ui = rule.can_add_pages = rule.can_add_sources = name == "pro"
            rule.max_sources = 5 if name == "pro" else 0
            rule.max_pages = 5 if name == "pro" else 3
            rule.max_elements_per_page = 12
        rule.save()
    # Legacy messages had no expiry. Close that retention hole during upgrade.
    Campaign = apps.get_model("core", "MessageCampaign")
    Campaign.objects.filter(expires_at__isnull=True).update(expires_at=timezone.now()+timedelta(hours=24))
    Event = apps.get_model("core", "WordPressSyncEvent")
    Event.objects.exclude(payload={}).update(payload={})


class Migration(migrations.Migration):
    dependencies = [("core", "0010_externaldatasource_unique_global_source_key")]
    operations = [migrations.RunPython(initialize, migrations.RunPython.noop)]
