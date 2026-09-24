# Gadget Price Platform
 
Django control panels and backend for market prices, company price lists, and ESP32 information displays.

New Persian guide: [Price platform, graphical setup and communication protocols](docs/bootstrap/18-price-platform.md).

Start private graphical setup with `make guided` (or `make test-setup`), then open `/setup/`. Application integrations and encrypted credentials are managed in the owner panel. Firmware source and the interactive Telegram bot are separate projects/stages.

## Detailed guides (separate files)
- Reliability fixes and upgrade notes: [docs/bootstrap/17-reliability-upgrade.md](docs/bootstrap/17-reliability-upgrade.md)
- Plain-language Linux deployment guide (Persian): [راهنمای-ساده-و-کامل.md](%D8%B1%D8%A7%D9%87%D9%86%D9%85%D8%A7%DB%8C-%D8%B3%D8%A7%D8%AF%D9%87-%D9%88-%DA%A9%D8%A7%D9%85%D9%84.md)
- Linux test + Mac browser guide (Persian): [راهنمای-تست-سرور-و-مرورگر.md](%D8%B1%D8%A7%D9%87%D9%86%D9%85%D8%A7%DB%8C-%D8%AA%D8%B3%D8%AA-%D8%B3%D8%B1%D9%88%D8%B1-%D9%88-%D9%85%D8%B1%D9%88%D8%B1%DA%AF%D8%B1.md)
- Graphical firmware update guide (Persian): [راهنمای-آپدیت-فریمور.md](%D8%B1%D8%A7%D9%87%D9%86%D9%85%D8%A7%DB%8C-%D8%A2%D9%BE%D8%AF%DB%8C%D8%AA-%D9%81%D8%B1%DB%8C%D9%85%D9%88%D8%B1.md)
- Complete server and integration guide (Persian): [docs/راهنمای-جامع-سرور-و-یکپارچه‌سازی.md](docs/%D8%B1%D8%A7%D9%87%D9%86%D9%85%D8%A7%DB%8C-%D8%AC%D8%A7%D9%85%D8%B9-%D8%B3%D8%B1%D9%88%D8%B1-%D9%88-%DB%8C%DA%A9%D9%BE%D8%A7%D8%B1%DA%86%D9%87%E2%80%8C%D8%B3%D8%A7%D8%B2%DB%8C.md)
- Main index: `docs/bootstrap/00-index.md`
- Prerequisites: `docs/bootstrap/01-prerequisites.md`
- Environment: `docs/bootstrap/02-environment.md`
- Docker Compose: `docs/bootstrap/03-docker-compose.md`
- Backend service: `docs/bootstrap/04-backend-service.md`
- PostgreSQL/Redis/MQTT: `docs/bootstrap/05-mqtt-redis-db.md`
- Makefile commands: `docs/bootstrap/06-makefile-commands.md`
- Quality and CI: `docs/bootstrap/07-quality-and-ci.md`
- Local runbook: `docs/bootstrap/08-runbook-local.md`
- Troubleshooting: `docs/bootstrap/09-troubleshooting.md`
- Security baseline: `docs/bootstrap/10-security-baseline.md`
- WordPress sync contract: `docs/bootstrap/11-wordpress-sync-contract.md`
- UI contract: `docs/bootstrap/12-ui-contract.md`
- Database schema: `docs/bootstrap/13-db-schema.md`
- Control panel: `docs/bootstrap/14-control-panel.md`

## Stack
- Django + Django REST Framework
- PostgreSQL
- Redis
- MQTT (Mosquitto)
- Docker Compose (single-command local setup)

## One-time setup
```bash
make bootstrap
```

## Run
```bash
make up
```

## Verify
- API health: `http://localhost:8000/api/v1/health/`
- Services list: `make ps`
- Logs: `make logs`

## Daily commands
- Migrate: `make migrate`
- Test: `make test`
- Lint: `make lint`
- Format: `make format`
- Stop stack: `make down`

## Why this is production-minded
- Reproducible environment (Docker)
- Graphical application configuration; automatically generated infrastructure secrets
- Service separation (API/DB/Cache/MQTT)
- Baseline CI for lint + tests
- Ready for secure OTA and device auth extensions

## Validation before public deployment

Run the PostgreSQL CI suite, real browser checks, external integration checks, MQTT ACL tests and on-device OTA checks. The SQLite demo is for local review only. See the new guide for limitations and migration notes.
