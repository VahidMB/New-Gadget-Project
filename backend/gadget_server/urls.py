from django.contrib import admin
from django.urls import include, path

from core import portal_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("panel/", portal_views.dashboard, name="panel-dashboard"),
    path("panel/devices/", portal_views.device_list, name="panel-device-list"),
    path("panel/devices/new/", portal_views.device_create, name="panel-device-create"),
    path("panel/devices/<int:pk>/", portal_views.device_detail, name="panel-device-detail"),
    path("panel/devices/<int:pk>/edit/", portal_views.device_edit, name="panel-device-edit"),
    path("panel/devices/<int:pk>/token/", portal_views.device_token_rotate, name="panel-device-token-rotate"),
    path("panel/devices/<int:pk>/token/success/", portal_views.device_token_success, name="panel-device-token-success"),
    path("panel/devices/<int:pk>/activation/", portal_views.device_activation_toggle, name="panel-device-activation-toggle"),
    path("panel/messages/", portal_views.message_list, name="panel-message-list"),
    path("panel/messages/new/", portal_views.message_create, name="panel-message-create"),
    path("panel/messages/<int:pk>/edit/", portal_views.message_edit, name="panel-message-edit"),
    path("panel/data-sources/", portal_views.data_source_list, name="panel-data-source-list"),
    path("panel/data-sources/new/", portal_views.data_source_create, name="panel-data-source-create"),
    path("panel/data-sources/<int:pk>/edit/", portal_views.data_source_edit, name="panel-data-source-edit"),
    path("panel/firmware/", portal_views.firmware_list, name="panel-firmware-list"),
    path("panel/firmware/upload/", portal_views.firmware_upload, name="panel-firmware-upload"),
    path("panel/companies/", portal_views.company_list, name="panel-company-list"),
    path("panel/companies/new/", portal_views.company_create, name="panel-company-create"),
    path("panel/users/", portal_views.user_list, name="panel-user-list"),
    path("panel/users/new/", portal_views.user_create, name="panel-user-create"),
    path("panel/memberships/", portal_views.membership_list, name="panel-membership-list"),
    path("panel/memberships/new/", portal_views.membership_create, name="panel-membership-create"),
    path("api/v1/", include("core.urls")),
]
