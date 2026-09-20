# 05) راهنمای PostgreSQL + Redis + MQTT

## PostgreSQL (`db`)
**وظیفه:** ذخیره‌سازی دائمی داده‌های سیستم (کاربران، دستگاه‌ها، تنظیمات، لاگ‌های ساختاریافته).  
**پیاده‌سازی فعلی:** سرویس مستقل با volume پایدار و healthcheck.

## Redis (`redis`)
**وظیفه:** کش سریع و backend صف (برای Celery در مراحل بعد).  
**پیاده‌سازی فعلی:** سرویس مستقل آماده اتصال از طریق `REDIS_URL`.

## MQTT (`mqtt`)
**وظیفه:** پیام‌رسانی realtime بین backend و گجت‌ها.  
**پیاده‌سازی فعلی:** Mosquitto با listener روی 1883 و websocket روی 9001.

## نقش نسبت به هم

- Backend مرکز تصمیم‌گیری است.
- PostgreSQL داده اصلی را نگه می‌دارد.
- Redis سرعت و queue را فراهم می‌کند.
- MQTT اعلان/پیام لحظه‌ای به دستگاه‌ها را می‌دهد.

## پیشنهاد برای گام بعد

- تعریف topic convention مثل:
  - `devices/{device_id}/commands`
  - `devices/{device_id}/status`
- فعال‌سازی auth در Mosquitto (به‌جای anonymous)
- اضافه کردن TLS برای MQTT در محیط production
