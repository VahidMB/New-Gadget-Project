SHELL := /bin/bash

.PHONY: bootstrap up down logs ps rebuild migrate shell superuser test lint format check

bootstrap:
	@[ -f .env ] || cp .env.example .env
	docker compose build

up:
	docker compose up -d

rebuild:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

migrate:
	docker compose exec api python manage.py migrate

shell:
	docker compose exec api python manage.py shell

superuser:
	docker compose exec api python manage.py createsuperuser

test:
	docker compose exec api pytest -q

lint:
	docker compose exec api ruff check .

format:
	docker compose exec api ruff format .

check: lint test

.PHONY: guided test-setup
guided:
	python3 scripts/guided_setup.py

test-setup:
	python3 scripts/guided_setup.py --test
