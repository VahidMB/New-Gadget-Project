# 08) Runbook اجرای لوکال (Step-by-Step)

## مرحله 1: آماده‌سازی

```bash
make bootstrap
```

## مرحله 2: بالا آوردن سرویس‌ها

```bash
make up
make ps
```

## مرحله 3: بررسی سلامت API

- URL: `http://localhost:8000/api/v1/health/`

یا با curl:

```bash
curl http://localhost:8000/api/v1/health/
```

## مرحله 4: تست سریع

```bash
make test
```

## مرحله 5: عملیات روزانه توسعه

- migration: `make migrate`
- logs: `make logs`
- stop: `make down`

## معیار موفقیت

- سرویس‌های `api`, `db`, `redis`, `mqtt` در وضعیت healthy/running باشند.
- endpoint سلامت پاسخ `200` بدهد.
- تست پایه پاس شود.
