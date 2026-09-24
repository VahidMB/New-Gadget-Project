from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.config_sync import refresh_all_device_configs, refresh_device_config
from core.models import DeviceProfile, UIElement, UIPage, UITemplate, WordPressDevice


@receiver(post_save, sender=WordPressDevice)
def device_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    refreshed = refresh_device_config(instance.pk, created=created)
    if refreshed:
        instance.effective_config = refreshed.effective_config
        instance.ui_version = refreshed.ui_version
        instance.config_sync_pending = refreshed.config_sync_pending


@receiver(post_save, sender=DeviceProfile)
@receiver(post_delete, sender=DeviceProfile)
def profile_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_device_config(instance.device_id)


@receiver(post_save, sender=UITemplate)
@receiver(post_delete, sender=UITemplate)
@receiver(post_save, sender=UIPage)
@receiver(post_delete, sender=UIPage)
@receiver(post_save, sender=UIElement)
@receiver(post_delete, sender=UIElement)
def template_changed(sender, raw=False, **kwargs):
    if not raw:
        # Recompute both plans, including the old plan when a template moves.
        refresh_all_device_configs()


from core.models import DevicePreference, SourceSelection  # noqa: E402

@receiver(post_save, sender=DevicePreference)
@receiver(post_delete, sender=DevicePreference)
@receiver(post_save, sender=SourceSelection)
@receiver(post_delete, sender=SourceSelection)
def preferences_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        refresh_device_config(instance.device_id)


from core.models import PlanRule, ExternalDataSource  # noqa: E402

@receiver(post_save, sender=PlanRule)
@receiver(post_delete, sender=PlanRule)
def rule_changed(sender, raw=False, **kwargs):
    if not raw:
        refresh_all_device_configs()


@receiver(post_save, sender=ExternalDataSource)
def source_definition_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        for device_id in instance.selections.values_list("device_id", flat=True):
            refresh_device_config(device_id)
