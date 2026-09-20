# Gadget Backend (Professional Bootstrap)

Backend and infrastructure baseline for an ESP32 gadget platform.

## Detailed guides (separate files)
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
- Environment-based configuration (`.env`)
- Service separation (API/DB/Cache/MQTT)
- Baseline CI for lint + tests
- Ready for secure OTA and device auth extensions

## Next implementation steps
1. Add `Device` model and per-device API key.
2. Add token/certificate-based device auth.
3. Add Celery worker and periodic data fetch jobs.
4. Add signed OTA metadata + firmware delivery endpoint.
5. Add Nginx reverse proxy with TLS in deployment.
