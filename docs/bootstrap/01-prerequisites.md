# 01) پیش‌نیازها

## هدف
اجرای کل استک با حداقل فرمان و بدون نصب دستی وابستگی‌ها در هر بار.

## پیش‌نیازهای سیستم

- Docker Desktop (macOS) با Docker Engine فعال
- Docker Compose V2
- Git
- حداقل 4GB RAM آزاد برای کانتینرها
- پورت‌های آزاد:
  - `8000` (API)
  - `5432` (PostgreSQL)
  - `6379` (Redis)
  - `1883` و `9001` (MQTT)

## چک سریع

```bash
docker --version
docker compose version
```

اگر خطای `Cannot connect to the Docker daemon` دیدید:
- Docker Desktop را باز کنید.
- صبر کنید Engine کاملاً بالا بیاید.
- دوباره دستورها را اجرا کنید.

## خروجی مورد انتظار

پس از آماده بودن پیش‌نیازها، با دو دستور زیر باید کل محیط بالا بیاید:

```bash
make bootstrap
make up
```
