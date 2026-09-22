# امنیت دستگاه، MQTT و OTA

## راه‌اندازی اولیه دستگاه

1. ابتدا دستگاه را از WordPress sync یا Django Admin بسازید.
2. برای تولید credential اختصاصی، در کانتینر API اجرا کنید:

```bash
docker compose exec api python manage.py provision_device DEVICE_ID
```

خروجی این دستور فقط یک‌بار توکن plaintext را نمایش می‌دهد. سرور فقط hash توکن را نگه می‌دارد. برای تعویض credential از گزینه `--rotate` استفاده کنید.

تمام endpointهای دستگاه باید هدر زیر را داشته باشند:

```text
X-Device-Token: <provisioned-token>
```

دستگاه inactive، suspended یا unprovisioned به endpointهای device دسترسی ندارد.

## قرارداد دستگاه

- `GET /api/v1/devices/{external_id}/display-config/`
- `POST /api/v1/devices/{external_id}/heartbeat/`
- `GET /api/v1/devices/{external_id}/firmware/update-check/?firmware_version=X.Y.Z`
- `POST /api/v1/devices/{external_id}/firmware/update-report/`

Heartbeat شامل `status`، `firmware_version`، `battery_level`، `signal_strength` و `config_version` است. Celery هر دقیقه دستگاه‌هایی را که بیشتر از `DEVICE_HEARTBEAT_STALE_AFTER_SECONDS` پیام نداده‌اند offline می‌کند.

## انتشار OTA

در Django Admin یک `Firmware Release` بسازید:

- `hardware_model` باید دقیقاً با مدل دستگاه برابر باشد.
- `version` برای همان مدل یکتا است.
- `download_url` باید HTTPS باشد.
- `checksum_sha256` باید هش کامل فایل firmware باشد.
- فقط releaseهای `is_active=true` به دستگاه پیشنهاد می‌شوند؛ `published_at` برای ثبت زمان انتشار و مرتب‌سازی استفاده می‌شود.

دستگاه ابتدا update-check را فراخوانی می‌کند، checksum فایل دریافتی را بررسی می‌کند و سپس نتیجه را با `update-report` ثبت می‌کند. وضعیت‌های قابل ثبت: `pending`، `downloading`، `installed`، `failed` و `skipped`.

## MQTT

تغییر کانفیگ WordPress برای دستگاه provisioned یک پیام QoS 1 retained در topic زیر منتشر می‌کند:

```text
gadget/v1/devices/{external_id}/commands/config
```

Payload شامل `type: config.changed` و `ui_version` است. دستگاه باید پس از دریافت پیام، endpoint نمایش کانفیگ را با توکن خود دریافت کند.

در production این مقادیر را تنظیم کنید:

```dotenv
MQTT_USERNAME=...
MQTT_PASSWORD=...
MQTT_USE_TLS=1
MQTT_TOPIC_ROOT=gadget/v1
```

برای production باید ACL broker نیز طوری تنظیم شود که هر دستگاه فقط topic اختصاصی خود را subscribe کند.

## عملیات

- Prometheus: `GET /api/v1/metrics/`، با `Authorization: Bearer <METRICS_TOKEN>` در صورت تنظیم توکن.
- بررسی دستی سلامت: `docker compose exec api python manage.py check_services`
- بررسی دستی دستگاه‌های stale: `docker compose exec api python manage.py check_stale_devices`
- Pull sync هر ۱۵ دقیقه توسط Celery Beat اجرا می‌شود.
