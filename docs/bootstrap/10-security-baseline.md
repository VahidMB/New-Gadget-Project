# 10) Security Baseline (شروع ایمن)

## هدف
همان ابتدای پروژه حداقل کنترل‌های امنیتی استاندارد فعال باشند.

## کنترل‌های ضروری

1. **TLS در همه ارتباطات production**
   - API فقط پشت HTTPS
   - MQTT با TLS

2. **مدیریت secrets**
   - عدم commit فایل `.env`
   - secret manager برای production

3. **Authentication و Authorization دستگاه**
   - هر دستگاه credential جدا
   - محدودسازی دسترسی هر دستگاه به منابع خودش

4. **امنیت OTA**
   - firmware signed
   - بررسی hash/signature قبل از نصب
   - rollback در صورت شکست update

5. **Harden کردن کانتینرها**
   - base image کوچک و به‌روز
   - اجرای سرویس‌ها با user غیر root (در گام بعد)
   - حداقل کردن پورت‌های expose شده

6. **Observability**
   - لاگ ساختاریافته
   - health checks
   - alert برای خطاهای مهم

## مواردی که در این baseline آماده شده

- تفکیک سرویس‌ها (API/DB/Redis/MQTT)
- env-based config
- تست سلامت API
- CI اولیه برای lint/test

## مواردی که باید در گام بعدی اضافه شود

- Device auth واقعی (token/cert)
- TLS termination با Nginx/Caddy
- MQTT authentication و ACL
- سیاست rotate برای کلیدها و رمزها
