# راهنمای بخش زیرساخت و اتوماسیون (Index)

این راهنما مخصوص بخشی است که الان پیاده‌سازی شده: راه‌اندازی حرفه‌ای Backend به‌صورت اتومات با Docker.

## نقشه فایل‌های راهنما

1. [01-prerequisites.md](./01-prerequisites.md)  
   پیش‌نیازها و چیزهایی که باید روی سیستم آماده باشد.

2. [02-environment.md](./02-environment.md)  
   مدیریت `.env` و تنظیمات محیط.

3. [03-docker-compose.md](./03-docker-compose.md)  
   توضیح سرویس‌ها و شبکه در `docker-compose.yml`.

4. [04-backend-service.md](./04-backend-service.md)  
   توضیح سرویس API، Dockerfile، entrypoint و ساختار Django.

5. [05-mqtt-redis-db.md](./05-mqtt-redis-db.md)  
   نقش PostgreSQL، Redis و MQTT و نحوه استفاده.

6. [06-makefile-commands.md](./06-makefile-commands.md)  
   همه فرمان‌های روزانه پروژه.

7. [07-quality-and-ci.md](./07-quality-and-ci.md)  
   lint، format، test، pre-commit و CI.

8. [08-runbook-local.md](./08-runbook-local.md)  
   Runbook مرحله‌به‌مرحله برای اجرای لوکال.

9. [09-troubleshooting.md](./09-troubleshooting.md)  
   رفع خطاهای رایج (از جمله Docker daemon).

10. [10-security-baseline.md](./10-security-baseline.md)  
    اصول امنیتی پایه برای شروع حرفه‌ای.

11. [11-wordpress-sync-contract.md](./11-wordpress-sync-contract.md)  
   بهترین روش Sync از WordPress + ذخیره داخلی + اعلان تغییرات.

12. [12-ui-contract.md](./12-ui-contract.md)  
   قرارداد UI نسخه‌دار برای simple و pro.

13. [13-db-schema.md](./13-db-schema.md)  
   نقشه کامل جدول‌های دیتابیس برای داده‌های داینامیک.

14. [14-control-panel.md](./14-control-panel.md)  
   راهنمای پنل کنترلی Django Admin.

15. [15-monitoring-and-health.md](./15-monitoring-and-health.md)  
   نظارت بر سلامت سرویس‌ها و دستگاه‌ها؛ dashboard status و heartbeat endpoint.

16. [16-device-security-ota.md](./16-device-security-ota.md)  
   Provisioning، توکن اختصاصی دستگاه، MQTT و فرآیند OTA.

## Scope فعلی

این مستندات فقط برای **زیرساخت اولیه استاندارد** هستند (Backend + Dependencies + Automation).  
Device Auth، OTA workflow، MQTT notification و monitoring عملیاتی نیز به این baseline افزوده شده‌اند.

- [18 — پنل قیمت، راه‌اندازی گرافیکی و پروتکل‌های جدید](18-price-platform.md)

- [19 — دریافت لحظه‌ای، بازر و تنظیم گرافیکی ارتباطات](19-live-buzzer-connections.md)

- [۲۰. مجوزهای انتخابی کارکنان سرور](20-staff-permissions.md)
