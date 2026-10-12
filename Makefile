.PHONY: setup build up down logs ps test integration lint smoke

setup:
	uv sync --dev
	cp -n .env.example .env || true

build:
	docker compose --env-file .env build

up:
	docker compose --env-file .env up -d

down:
	docker compose --env-file .env down

logs:
	docker compose --env-file .env logs -f

ps:
	docker compose --env-file .env ps

test:
	uv run pytest tests/unit

integration:
	GRIDEYE_INTEGRATION=1 uv run pytest tests/integration

lint:
	uv run ruff check .
	uv run mypy grideye_shared services simulation

smoke:
	uv run python scripts/smoke_test.py

