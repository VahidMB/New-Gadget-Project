# 04) راهنمای سرویس Backend

## هدف
ارائه API پایدار برای گجت‌ها + نقطه شروع توسعه حرفه‌ای.

## فایل‌های کلیدی

- `backend/Dockerfile`
- `backend/entrypoint.sh`
- `backend/requirements.txt`
- `backend/manage.py`
- `backend/gadget_server/settings.py`
- `backend/gadget_server/urls.py`
- `backend/core/views.py`

## نحوه اجرا در کانتینر

1. نصب dependencyها از `requirements.txt`
2. انتظار برای آماده شدن PostgreSQL
3. اجرای migration
4. اجرای collectstatic
5. اجرای gunicorn روی `0.0.0.0:8000`

## endpoint فعلی

- `GET /api/v1/health/` → وضعیت سرویس

نمونه پاسخ:

```json
{
  "status": "ok",
  "service": "gadget-api"
}
```

## توسعه بعدی پیشنهادی

- مدل `Device`
- احراز هویت per-device
- endpoint دریافت config/device payload
- endpoint دریافت firmware metadata برای OTA
