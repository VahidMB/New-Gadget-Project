from django.contrib import admin

from core.access import is_platform_user, scope_by_company, visible_companies
from core.models import (
    Company,
    CompanyMembership,
    DeviceProfile,
    DeviceStatus,
    ExternalDataSource,
    FirmwareDeployment,
    FirmwareRelease,
    MessageCampaign,
    PlanRule,
    ServiceHealth,
    SyncNotification,
    UIElement,
    UIPage,
    UITemplate,
    WordPressDataSource,
    WordPressDevice,
    WordPressSyncEvent,
)


class PlatformOnlyAdmin(admin.ModelAdmin):
    """Keep platform/company administration out of company-user admin views."""

    def has_module_permission(self, request):
        return is_platform_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_platform_user(request.user)

    def has_add_permission(self, request):
        return is_platform_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_platform_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_platform_user(request.user)


class CompanyScopedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return scope_by_company(request.user, super().get_queryset(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "company":
            kwargs["queryset"] = visible_companies(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "target_devices":
            kwargs["queryset"] = scope_by_company(request.user, WordPressDevice.objects.all())
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(Company)
class CompanyAdmin(PlatformOnlyAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(PlatformOnlyAdmin):
    list_display = ("user", "company", "role", "is_active", "created_at")
    search_fields = ("user__username", "user__email", "company__name")
    list_filter = ("role", "is_active", "company")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ExternalDataSource)
class ExternalDataSourceAdmin(CompanyScopedAdmin):
    list_display = ("name", "company", "source_type", "endpoint_url", "is_active", "updated_at")
    search_fields = ("name", "company__name", "endpoint_url")
    list_filter = ("company", "source_type", "is_active")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MessageCampaign)
class MessageCampaignAdmin(CompanyScopedAdmin):
    list_display = ("name", "company", "status", "scheduled_at", "created_by", "created_at")
    search_fields = ("name", "message", "company__name")
    list_filter = ("company", "status")
    readonly_fields = ("created_at", "updated_at")


class UIElementInline(admin.TabularInline):
    model = UIElement
    extra = 0


class UIPageInline(admin.StackedInline):
    model = UIPage
    extra = 0
    show_change_link = True


class DeviceProfileInline(admin.StackedInline):
    model = DeviceProfile
    extra = 0
    max_num = 1


class DeviceStatusInline(admin.StackedInline):
    model = DeviceStatus
    extra = 0
    max_num = 1
    can_delete = False
    readonly_fields = ("status", "last_heartbeat_at", "last_config_version", "firmware_version", "battery_level", "signal_strength", "updated_at")


class FirmwareDeploymentInline(admin.TabularInline):
    model = FirmwareDeployment
    extra = 0
    readonly_fields = ("release", "status", "reported_version", "error_message", "last_reported_at", "created_at", "updated_at")
    can_delete = False


@admin.register(ServiceHealth)
class ServiceHealthAdmin(admin.ModelAdmin):
    list_display = ("get_service_display", "status", "response_time_ms", "last_check_at", "failed_count")
    search_fields = ("service_name",)
    list_filter = ("status", "service_name")
    readonly_fields = ("last_check_at", "check_count", "failed_count")

    def get_service_display(self, obj):
        return obj.get_service_name_display()

    get_service_display.short_description = "Service"


@admin.register(DeviceStatus)
class DeviceStatusAdmin(admin.ModelAdmin):
    list_display = ("device", "status", "last_heartbeat_at", "last_config_version", "firmware_version", "battery_level", "signal_strength")
    search_fields = ("device__external_id", "device__name", "firmware_version")
    list_filter = ("status", "updated_at")
    readonly_fields = ("updated_at",)


@admin.register(WordPressDevice)
class WordPressDeviceAdmin(CompanyScopedAdmin):
    list_display = ("external_id", "company", "name", "hardware_model", "provisioning_state", "plan", "is_active", "ui_version", "last_synced_at")
    search_fields = ("external_id", "name", "serial_number", "customer_external_id", "hardware_model")
    list_filter = ("provisioning_state", "hardware_model", "plan", "is_active", "ui_version")
    list_editable = ("name", "plan", "is_active", "ui_version")
    inlines = [DeviceProfileInline, DeviceStatusInline, FirmwareDeploymentInline]
    readonly_fields = ("device_token_hash", "device_token_created_at", "last_synced_at", "created_at", "updated_at", "effective_config")
    fieldsets = (
        ("Identity", {"fields": ("company", "external_id", "customer_external_id", "serial_number", "hardware_model", "name")}),
        ("Provisioning", {"fields": ("provisioning_state", "device_token_hash", "device_token_created_at")}),
        ("Subscription", {"fields": ("plan", "is_active", "ui_version")}),
        (
            "WordPress Sync",
            {
                "fields": (
                    "metadata",
                    "custom_config",
                    "effective_config",
                    "last_wordpress_updated_at",
                    "last_synced_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(WordPressDataSource)
class WordPressDataSourceAdmin(admin.ModelAdmin):
    list_display = ("external_id", "key", "label", "enabled", "last_synced_at")
    search_fields = ("external_id", "key", "label")
    list_filter = ("enabled",)
    list_editable = ("enabled", "key", "label")
    readonly_fields = ("last_synced_at", "created_at", "updated_at")


@admin.register(PlanRule)
class PlanRuleAdmin(admin.ModelAdmin):
    list_display = (
        "plan_name",
        "can_customize_ui",
        "can_change_theme",
        "can_add_pages",
        "can_add_sources",
        "max_pages",
        "max_elements_per_page",
        "max_sources",
        "is_active",
    )
    list_editable = ("can_customize_ui", "can_change_theme", "can_add_pages", "can_add_sources", "max_pages", "max_elements_per_page", "max_sources", "is_active")
    search_fields = ("plan_name",)


@admin.register(WordPressSyncEvent)
class WordPressSyncEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "entity_type", "entity_external_id", "source", "status", "created_at")
    search_fields = ("event_type", "entity_external_id")
    list_filter = ("source", "entity_type", "status")
    readonly_fields = ("event_type", "entity_type", "entity_external_id", "source", "payload", "payload_hash", "status", "message", "created_at", "processed_at")


@admin.register(SyncNotification)
class SyncNotificationAdmin(admin.ModelAdmin):
    list_display = ("category", "title", "delivered", "created_at", "delivered_at")
    search_fields = ("title", "message")
    list_filter = ("category", "delivered")
    readonly_fields = ("created_at", "delivered_at")


@admin.register(UITemplate)
class UITemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "plan_type", "is_active", "updated_at")
    search_fields = ("name", "version", "plan_type")
    list_filter = ("plan_type", "is_active")
    inlines = [UIPageInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(UIPage)
class UIPageAdmin(admin.ModelAdmin):
    list_display = ("template", "page_key", "page_type", "priority", "is_active")
    search_fields = ("page_key", "page_type", "template__name")
    list_filter = ("page_type", "is_active", "template")
    inlines = [UIElementInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(UIElement)
class UIElementAdmin(admin.ModelAdmin):
    list_display = ("page", "element_type", "label", "source_key", "z_index", "is_visible")
    search_fields = ("element_type", "label", "source_key", "page__page_key")
    list_filter = ("element_type", "is_visible", "page__template")
    list_editable = ("label", "source_key", "z_index", "is_visible")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FirmwareRelease)
class FirmwareReleaseAdmin(admin.ModelAdmin):
    list_display = ("hardware_model", "version", "is_active", "is_mandatory", "published_at", "updated_at")
    search_fields = ("hardware_model", "version")
    list_filter = ("is_active", "is_mandatory", "hardware_model")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FirmwareDeployment)
class FirmwareDeploymentAdmin(admin.ModelAdmin):
    list_display = ("device", "release", "status", "reported_version", "last_reported_at", "updated_at")
    search_fields = ("device__external_id", "release__hardware_model", "release__version", "reported_version")
    list_filter = ("status", "release__hardware_model")
    readonly_fields = ("created_at", "updated_at")
