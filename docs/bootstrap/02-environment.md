# 02) تنظیمات محیط (`.env`)

## هدف
جدا کردن تنظیمات از کد برای توسعه، تست، و استقرار حرفه‌ای.

## فایل‌های مرتبط

- `.env.example` → قالب تنظیمات
- `.env` → مقدار واقعی (نباید commit شود)

## تنظیمات فعلی

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `REDIS_URL`
- `MQTT_HOST`
- `MQTT_PORT`

## روش استفاده

1. اولین بار:
```bash
cp .env.example .env
```
2. مقدارهای حساس را تغییر بدهید (به‌خصوص `DJANGO_SECRET_KEY` و پسورد دیتابیس).
3. سرویس‌ها را بالا بیاورید.

## نکات استاندارد

- هیچ‌وقت `.env` را در Git commit نکنید.
- برای prod از secret manager استفاده کنید.
- برای هر محیط (dev/staging/prod) فایل env جدا داشته باشید.
