# 06) راهنمای `Makefile`

## هدف
کاهش خطای انسانی و یکسان‌سازی workflow تیم.

## فرمان‌ها

- `make bootstrap`
  - اگر `.env` وجود نداشته باشد از `.env.example` کپی می‌کند
  - imageها را build می‌کند

- `make up`
  - کل سرویس‌ها را در background بالا می‌آورد

- `make rebuild`
  - با build مجدد سرویس‌ها را بالا می‌آورد

- `make down`
  - سرویس‌ها را متوقف می‌کند

- `make logs`
  - لاگ‌های تجمیعی سرویس‌ها

- `make ps`
  - وضعیت سرویس‌ها

- `make migrate`
  - اجرای migration

- `make shell`
  - ورود به Django shell

- `make superuser`
  - ساخت ادمین

- `make lint`
  - بررسی کیفیت با Ruff

- `make format`
  - فرمت کد

- `make test`
  - اجرای تست‌ها

- `make check`
  - lint + test

## ترتیب پیشنهادی روز اول

```bash
make bootstrap
make up
make ps
make test
```
