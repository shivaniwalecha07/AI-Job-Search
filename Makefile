.PHONY: install db-up db-down migrate discover discover-supervised digest test lint fmt

install:
	python3 -m pip install -e ".[dev]"

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	alembic upgrade head

# Unattended lane (cron): only non-supervised connectors
discover:
	job-agent run --stage discovery

# Supervised lane: includes LinkedIn (you must be present + logged in)
discover-supervised:
	job-agent run --supervised

digest:
	job-agent run --stage digest

test:
	pytest -q

lint:
	ruff check src tests
	mypy src

fmt:
	ruff format src tests
