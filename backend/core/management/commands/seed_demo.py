import json
import secrets
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from core.models import (Company, CompanyMembership, WordPressDevice, DeviceStatus, PlatformSettings, ExternalDataSource, SourceSelection, DevicePreference, PriceList, PriceItem, PlanRule, UITemplate, UIPage, UIElement, MessageCampaign)
from core.access import rule_for
from core.source_engine import store_value


class Command(BaseCommand):
    help = "Create clearly labeled sample data for the local demo profile only."
    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "gadget_server.demo_settings":
            raise CommandError("Use --settings=gadget_server.demo_settings; demo seeding is disabled in production.")
        password = secrets.token_urlsafe(18)
        with transaction.atomic():
            PlatformSettings.objects.update_or_create(pk=1, defaults={"site_name": "گجت من", "test_mode": True, "setup_complete": True, "timezone": "Asia/Tehran"})
            users = {}
            for username, first, last in [("admin", "وحید", "مدیر پلتفرم"), ("maryam", "مریم", "رضایی"), ("aria", "علی", "مدیر شرکت آریا"), ("simple", "سارا", "احمدی")]:
                user, _ = get_user_model().objects.get_or_create(username=username)
                user.first_name, user.last_name = first, last
                user.is_superuser = user.is_staff = username == "admin"
                user.set_password(password)
                user.save()
                users[username] = user
            personal, _ = Company.objects.get_or_create(slug="maryam", defaults={"name": "حساب شخصی مریم", "account_kind": "personal"})
            basic, _ = Company.objects.get_or_create(slug="sara", defaults={"name": "حساب شخصی سارا", "account_kind": "personal"})
            business, _ = Company.objects.get_or_create(slug="aria", defaults={"name": "شرکت آریا", "account_kind": "business"})
            branch, _ = Company.objects.get_or_create(slug="aria-tehran", defaults={"name": "نمایندگی تهران", "parent": business})
            for username, company, role in [("maryam", personal, "member"), ("simple", basic, "member"), ("aria", business, "company_admin")]:
                CompanyMembership.objects.get_or_create(user=users[username], company=company, defaults={"role": role})
            for plan in ["simple", "pro"]:
                if not PlanRule.objects.filter(plan_name=plan).exists():
                    rule_for(plan).save()
            devices = []
            for index, (name, company, assigned, plan, recipient) in enumerate([
                ("گجت شخصی مریم", personal, users["maryam"], "pro", "مریم رضایی"),
                ("گجت شخصی سارا", basic, users["simple"], "simple", "سارا احمدی"),
                ("نمایندگی مرکزی", business, None, "pro", "علی رضایی"),
                ("نمایندگی شیراز", business, None, "pro", "سارا محمدی"),
                ("نمایندگی اصفهان", business, None, "pro", "رضا احمدی"),
                ("گجت شعبه تهران", branch, None, "pro", "مهدی کریمی"),
            ]):
                device, _ = WordPressDevice.objects.get_or_create(external_id=f"DEMO-{index+1:03d}", defaults={"name": name, "company": company, "assigned_user": assigned, "plan": plan, "recipient_name": recipient, "hardware_model": "esp32-s3", "group_name": "نمایندگان" if index > 1 else "شخصی"})
                DeviceStatus.objects.update_or_create(device=device, defaults={"status": "online" if index != 3 else "offline", "last_heartbeat_at": timezone.now() if index != 3 else timezone.now()-timedelta(minutes=20), "firmware_version": "2.1.0", "signal_strength": -52})
                DevicePreference.objects.get_or_create(device=device)
                devices.append(device)
            for key, name, value, unit in [("gold", "طلای ۱۸ عیار", "6500000", "تومان / گرم"), ("usd", "دلار آمریکا", "95000", "تومان / دلار"), ("btc", "بیت‌کوین", "85000", "دلار / BTC")]:
                source, _ = ExternalDataSource.objects.get_or_create(company=None, display_key=key, defaults={"name": name, "source_type": "internal", "category": "price", "ttl_seconds": 3600, "unit": unit})
                store_value(source, {"title": name, "value": value, "unit": unit})
                for device in devices:
                    SourceSelection.objects.get_or_create(device=device, source=source)
            for company, target in [(personal, devices[0]), (business, devices[2])]:
                price_list, _ = PriceList.objects.get_or_create(company=company, name="لیست قیمت شرکت آریا", defaults={"revision": 12})
                price_list.target_devices.add(target)
                for code, name, amount in [("AR-CB-001", "کابل شبکه", "250000"), ("AR-AD-002", "آداپتور", "480000"), ("AR-SW-003", "سوئیچ شبکه", None)]:
                    PriceItem.objects.update_or_create(price_list=price_list, code=code, defaults={"name": name, "amount": amount, "unit": "تومان", "valid_until": timezone.now()+timedelta(hours=1) if amount else timezone.now()-timedelta(minutes=5)})
            for plan in ["simple", "pro"]:
                template, _ = UITemplate.objects.get_or_create(name="قالب سرمه‌ای " + plan, plan_type=plan)
                page, _ = UIPage.objects.get_or_create(template=template, page_key="market", defaults={"page_type": "market"})
                UIElement.objects.get_or_create(page=page, label="قیمت طلا", defaults={"element_type": "price", "source_key": "gold", "width": 280, "height": 80})
            campaign, _ = MessageCampaign.objects.get_or_create(company=business, name="لیست قیمت فردا", defaults={"message": "لیست قیمت جدید نمایندگان منتشر شد.", "scheduled_at": timezone.now()+timedelta(days=1), "expires_at": timezone.now()+timedelta(days=2), "status": "scheduled"})
            campaign.target_devices.add(devices[2], devices[3])
        path = Path(settings.BASE_DIR) / "runtime" / "demo-credentials.json"
        path.write_text(json.dumps({"password": password, "users": list(users)}))
        path.chmod(0o600)
        self.stdout.write("Local demo created; credentials are in the protected runtime/demo-credentials.json file.")
