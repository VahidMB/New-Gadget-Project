from django.contrib.auth import get_user_model
from django.test import Client

from core.access import scope_by_company
from core.models import Company, CompanyMembership, ExternalDataSource, MessageCampaign, WordPressDevice


def _user(username: str):
    return get_user_model().objects.create_user(username=username, password="test-password")


def _company_user(company: Company, username: str):
    user = _user(username)
    CompanyMembership.objects.create(user=user, company=company, role=CompanyMembership.Role.COMPANY_ADMIN)
    return user


def _platform_owner(username: str):
    user = _user(username)
    CompanyMembership.objects.create(user=user, role=CompanyMembership.Role.OWNER)
    return user


def test_company_user_only_sees_own_business_records_in_panel() -> None:
    first = Company.objects.create(name="First Company", slug="first")
    second = Company.objects.create(name="Second Company", slug="second")
    user = _company_user(first, "company-admin")
    WordPressDevice.objects.create(company=first, external_id="first-device", name="First device")
    WordPressDevice.objects.create(company=second, external_id="second-device", name="Second device")
    MessageCampaign.objects.create(company=first, name="First campaign", message="Hello")
    MessageCampaign.objects.create(company=second, name="Second campaign", message="Hidden")
    ExternalDataSource.objects.create(
        company=first,
        name="First source",
        display_key="first.source",
        endpoint_url="https://first.example.test",
    )
    ExternalDataSource.objects.create(
        company=second,
        name="Second source",
        display_key="second.source",
        endpoint_url="https://second.example.test",
    )

    client = Client()
    client.force_login(user)

    device_response = client.get("/panel/devices/")
    message_response = client.get("/panel/messages/")
    source_response = client.get("/panel/data-sources/")

    assert device_response.status_code == 200
    assert "First device" in device_response.content.decode()
    assert "Second device" not in device_response.content.decode()
    assert "First campaign" in message_response.content.decode()
    assert "Second campaign" not in message_response.content.decode()
    assert "First source" in source_response.content.decode()
    assert "Second source" not in source_response.content.decode()


def test_platform_employee_query_scope_includes_every_company() -> None:
    first = Company.objects.create(name="First Company", slug="first")
    second = Company.objects.create(name="Second Company", slug="second")
    employee = _user("employee")
    CompanyMembership.objects.create(user=employee, role=CompanyMembership.Role.EMPLOYEE)
    WordPressDevice.objects.create(company=first, external_id="first-device")
    WordPressDevice.objects.create(company=second, external_id="second-device")

    visible = scope_by_company(employee, WordPressDevice.objects.all())

    assert set(visible.values_list("external_id", flat=True)) == {"first-device", "second-device"}


def test_company_user_cannot_open_company_admin_page() -> None:
    company = Company.objects.create(name="First Company", slug="first")
    user = _company_user(company, "staff-company-admin")
    user.is_staff = True
    user.save(update_fields=["is_staff"])

    response = Client().get("/admin/core/company/", follow=False)
    assert response.status_code == 302

    client = Client()
    client.force_login(user)
    response = client.get("/admin/core/company/")

    assert response.status_code == 403


def test_company_user_is_denied_platform_portal_controls() -> None:
    company = Company.objects.create(name="First Company", slug="first")
    user = _company_user(company, "limited-company-admin")
    client = Client()
    client.force_login(user)

    for path in ("/panel/companies/", "/panel/users/", "/panel/memberships/", "/panel/devices/new/"):
        assert client.get(path).status_code == 403


def test_company_user_cannot_edit_another_company_device_campaign_or_source() -> None:
    first = Company.objects.create(name="First Company", slug="first")
    second = Company.objects.create(name="Second Company", slug="second")
    user = _company_user(first, "scoped-editor")
    foreign_device = WordPressDevice.objects.create(company=second, external_id="other-device")
    foreign_campaign = MessageCampaign.objects.create(company=second, name="Other campaign", message="Hidden")
    foreign_source = ExternalDataSource.objects.create(
        company=second,
        name="Other source",
        display_key="other.source",
        endpoint_url="https://other.example.test",
    )
    client = Client()
    client.force_login(user)

    assert client.get(f"/panel/devices/{foreign_device.pk}/").status_code == 404
    assert client.get(f"/panel/devices/{foreign_device.pk}/edit/").status_code == 404
    assert client.get(f"/panel/messages/{foreign_campaign.pk}/edit/").status_code == 404
    assert client.get(f"/panel/data-sources/{foreign_source.pk}/edit/").status_code == 404


def test_device_token_is_shown_only_once_after_owner_provisions_device() -> None:
    owner = _platform_owner("platform-owner")
    device = WordPressDevice.objects.create(external_id="provision-me")
    client = Client()
    client.force_login(owner)

    response = client.post(f"/panel/devices/{device.pk}/token/", follow=True)

    assert response.status_code == 200
    assert "توکن دستگاه صادر شد" in response.content.decode()
    device.refresh_from_db()
    assert device.provisioning_state == WordPressDevice.ProvisioningState.PROVISIONED
    assert device.device_token_hash
    assert client.get(f"/panel/devices/{device.pk}/token/success/").status_code == 302
