# 11) قرارداد اتصال WordPress به سرور اصلی

## هدف
وردپرس منبع اصلی داده باشد، اما سرور اصلی نسخه عملیاتی خودش را در دیتابیس نگه دارد و در هر تغییر اطلاع بدهد.

## الگوی پیشنهادی حرفه‌ای

1. **Webhook (Realtime)**
   - WordPress در هر create/update/delete برای device یا data source به این مسیر POST می‌زند:
   - `POST /api/v1/integrations/wordpress/webhook/`
   - هدرهای امنیتی:
     - `X-WP-Timestamp`
     - `X-WP-Signature` (HMAC-SHA256 روی `timestamp.body`)

2. **Pull Sync (Recovery/Consistency)**
   - به صورت زمان‌بندی‌شده (مثلاً هر 15 دقیقه) سرور اصلی pull می‌کند:
   - `POST /api/v1/integrations/wordpress/sync/`
   - هدر امنیتی: `X-Sync-Token`
   - از endpointهای وردپرس داده devices/data-sources را می‌گیرد و upsert می‌کند.

3. **Notification on Change**
   - هر بار که رکورد `created/updated` شود:
     - در جدول `SyncNotification` ذخیره می‌شود.
     - اگر `SYNC_NOTIFY_WEBHOOK_URL` تنظیم باشد، webhook خروجی هم ارسال می‌شود.

## داده‌هایی که در سرور ذخیره می‌شود

- `WordPressDevice`
- `WordPressDataSource`
- `WordPressSyncEvent` (audit trail)
- `SyncNotification` (اطلاع‌رسانی)

## چرا این روش بهترین است

- webhook → سرعت بالا و نزدیک realtime
- pull sync → جبران قطعی موقت یا از دست رفتن event
- local DB mirror → استقلال عملیاتی سرور گجت از وردپرس
- audit + notification → قابل ردیابی و قابل مانیتور
