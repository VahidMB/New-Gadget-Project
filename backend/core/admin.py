from django.contrib import admin

from core.models import (
    DeviceProfile,
    DeviceStatus,
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
    readonly_fields = ("status", "last_heartbeat_at", "firmware_version", "battery_level", "signal_strength", "updated_at")


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
    list_display = ("device", "status", "last_heartbeat_at", "firmware_version", "battery_level", "signal_strength")
    search_fields = ("device__external_id", "device__name", "firmware_version")
    list_filter = ("status", "updated_at")
    readonly_fields = ("updated_at")


@admin.register(WordPressDevice)
class WordPressDeviceAdmin(admin.ModelAdmin):
    list_display = ("external_id", "name", "plan", "is_active", "ui_version", "last_synced_at")
    search_fields = ("external_id", "name", "serial_number", "customer_external_id")
    list_filter = ("plan", "is_active", "ui_version")
    list_editable = ("name", "plan", "is_active", "ui_version")
    inlines = [DeviceProfileInline, DeviceStatusInline]
        ("WordPress Sync", {"fields": ("metadata", "custom_config", "effective_config", "last_wordpress_updated_at", "last_synced_at", "created_at", "updated_at")}),
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
