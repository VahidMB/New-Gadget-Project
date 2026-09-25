from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse, get_resolver
from core.models import CompanyMembership, StaffAccess, AuditEvent
from core.staff_access import ROUTES, OWNER_ROUTES, route_allowed


@pytest.fixture
def staff():
    user = get_user_model().objects.create_user(username='limited', password='test-pass-not-real')
    CompanyMembership.objects.create(user=user, role='employee')
    client = Client()
    client.force_login(user)
    return user, client


@pytest.fixture
def owner():
    user = get_user_model().objects.create_superuser(username='boss', password='test-pass-not-real')
    client = Client()
    client.force_login(user)
    return user, client


def grant(user, *permissions):
    StaffAccess.objects.update_or_create(user=user, defaults={'permissions': list(permissions)})


def test_employee_denied_by_default_and_dashboard_has_no_admin_data(staff):
    _, client = staff
    response = client.get('/panel/')
    assert response.status_code == 200
    assert 'core/portal/staff_dashboard.html' in [t.name for t in response.templates]
    for url in ['/panel/users/', '/panel/firmware/', '/panel/devices/', '/panel/live/?device=1', '/panel/settings/']:
        assert client.get(url).status_code == 403
    assert client.post('/panel/firmware/upload/', {}).status_code == 403
    assert b'/panel/firmware/' not in response.content


def test_firmware_view_does_not_allow_upload_and_revocation_is_immediate(staff):
    user, client = staff
    grant(user, 'firmware.view')
    assert client.get('/panel/firmware/').status_code == 200
    assert b'/panel/firmware/upload/' not in client.get('/panel/firmware/').content
    assert client.post('/panel/firmware/upload/', {}).status_code == 403
    grant(user, 'firmware.upload')
    assert client.get('/panel/firmware/upload/').status_code == 200
    grant(user)
    assert client.get('/panel/firmware/').status_code == 403


def test_owner_saves_checkbox_grants_and_empty_submission_revokes(staff, owner):
    user, client = staff
    _, boss = owner
    url = reverse('panel-user-access', args=[user.pk])
    assert client.post(url, {'permissions': ['settings.manage']}).status_code == 403
    assert boss.get(url).status_code == 200
    assert boss.post(url, {'permissions': ['firmware.view', 'users.create']}).status_code == 302
    assert set(StaffAccess.objects.get(user=user).permissions) == {'firmware.view', 'users.create'}
    assert AuditEvent.objects.filter(action='staff.permissions').exists()
    assert boss.post(url, {'permissions': ['invented.admin']}).status_code == 200
    assert set(StaffAccess.objects.get(user=user).permissions) == {'firmware.view', 'users.create'}
    assert boss.post(url, {}).status_code == 302
    assert StaffAccess.objects.get(user=user).permissions == []


def test_delegated_user_creation_cannot_grant_privileges(staff):
    user, client = staff
    grant(user, 'users.create')
    response = client.post('/panel/users/new/', {'username': 'ordinary', 'password': 'Nontrivial-password-2026!', 'is_active': 'on', 'is_superuser': 'on', 'is_staff': 'on', 'permissions': ['settings.manage']})
    assert response.status_code == 302
    new = get_user_model().objects.get(username='ordinary')
    assert not new.is_superuser and not new.is_staff
    assert not new.company_memberships.exists()
    assert not StaffAccess.objects.filter(user=new).exists()
    assert client.get(reverse('panel-user-edit', args=[new.pk])).status_code == 403
    assert client.post('/panel/memberships/new/', {}).status_code == 403


@pytest.mark.parametrize('active', [True, False])
def test_employee_cannot_take_over_privileged_accounts(staff, owner, active):
    user, client = staff
    boss, _ = owner
    boss.is_active = active
    boss.save()
    grant(user, 'users.edit')
    for target in [boss, user]:
        assert client.post(reverse('panel-user-edit', args=[target.pk]), {'username': 'hijack'}).status_code == 403
    user.is_staff = True
    user.save()
    assert client.get('/admin/').status_code == 403


def test_route_catalog_covers_every_panel_endpoint():
    names = {p.name for p in get_resolver().url_patterns if getattr(p, 'name', '') and p.name.startswith('panel-')}
    assert names == set(ROUTES) | OWNER_ROUTES | {'panel-dashboard'}


@pytest.mark.parametrize('permission,url', [
    ('devices.view', '/panel/devices/'), ('users.view', '/panel/users/'),
    ('companies.view', '/panel/companies/'), ('sources.view', '/panel/data-sources/'),
    ('prices.view', '/panel/prices/'), ('messages.view', '/panel/messages/'),
    ('templates.view', '/panel/templates/'), ('monitoring.view', '/panel/monitoring/'),
    ('integrations.manage', '/panel/integrations/'), ('connections.manage', '/panel/connections/'),
    ('settings.manage', '/panel/settings/'), ('plans.manage', '/panel/plans/'),
])
def test_individual_grant_opens_only_selected_section(staff, permission, url):
    user, client = staff
    grant(user, permission)
    with patch('core.config_sync.refresh_all_device_configs'):
        assert client.get(url).status_code == 200
    assert not route_allowed(user, 'panel-membership-list')
    assert client.get('/panel/firmware/').status_code == 403


def test_owner_stays_full_access_without_grants(owner):
    user, client = owner
    assert route_allowed(user, 'panel-firmware-upload')
    assert client.get('/panel/users/').status_code == 200
    assert client.get(reverse('panel-user-access', args=[user.pk])).status_code == 403


def test_all_panel_routes_reject_ungranted_employee_get_and_post(staff):
    _, client = staff
    for route in get_resolver().url_patterns:
        if getattr(route, 'name', None) not in set(ROUTES) | OWNER_ROUTES:
            continue
        kwargs = {key: 1 for key in route.pattern.converters}
        url = reverse(route.name, kwargs=kwargs)
        assert client.get(url).status_code == 403, route.name
        assert client.post(url, {}).status_code == 403, route.name


def test_portal_templates_compile():
    from django.template.loader import get_template
    from django.conf import settings
    for path in (settings.BASE_DIR / 'core/templates/core/portal').glob('*.html'):
        get_template('core/portal/' + path.name)
