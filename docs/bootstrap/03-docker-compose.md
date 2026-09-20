# 03) راهنمای `docker-compose.yml`

## هدف
بالا آوردن همه اجزا با یک تعریف واحد و تکرارپذیر.

## سرویس‌ها

### `api`
- Build از `backend/Dockerfile`
- خواندن تنظیمات از `.env`
- وابسته به `db`, `redis`, `mqtt`
- پورت: `8000:8000`

### `db`
- تصویر: `postgres:16-alpine`
- volume دائمی: `postgres_data`
- healthcheck با `pg_isready`
- پورت: `5432:5432`

### `redis`
- تصویر: `redis:7-alpine`
- پورت: `6379:6379`

### `mqtt`
- تصویر: `eclipse-mosquitto:2`
- کانفیگ از `infra/mosquitto/mosquitto.conf`
- پورت‌ها: `1883`, `9001`

## چرا این طراحی استاندارد است

- تفکیک سرویس‌ها (Separation of Concerns)
- وابستگی‌ها مشخص و قابل کنترل
- دیتابیس با volume پایدار
- قابل توسعه برای staging/prod

## فرمان‌های کلیدی

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f --tail=200
docker compose down
```
