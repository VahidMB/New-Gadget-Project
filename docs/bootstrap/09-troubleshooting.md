# 09) Troubleshooting

## 1) خطای Docker daemon

**خطا:** `Cannot connect to the Docker daemon`  
**علت:** Docker Desktop خاموش است یا Engine بالا نیامده.

**راه‌حل:**
1. Docker Desktop را باز کنید.
2. صبر کنید تا Engine Running شود.
3. دوباره:
```bash
make up
```

## 2) اشغال بودن پورت

**نشانه:** سرویس بالا نمی‌آید و خطای bind روی پورت می‌دهد.

**راه‌حل:**
- پورت را آزاد کنید یا در `docker-compose.yml` تغییر دهید.

## 3) خطای اتصال API به دیتابیس

**نشانه:** migration fail یا خطای connection refused

**راه‌حل:**
- بررسی مقدارهای `.env`
- وضعیت `db` با `make ps`
- مشاهده لاگ: `make logs`

## 4) تست‌ها fail می‌شوند

**راه‌حل سریع:**
```bash
make down
docker compose rm -f
make up
make test
```

## 5) مشکل permission روی فایل‌ها (macOS)

- مطمئن شوید پروژه روی مسیری است که Docker Desktop اجازه دسترسی دارد.
- در تنظیمات Docker Desktop مسیر پروژه را Share کنید.
