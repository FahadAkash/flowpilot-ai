.PHONY: install-backend install-frontend dev-api dev-frontend test lint typecheck benchmark docker-up docker-down

install-backend:
	uv sync --directory backend --extra dev

install-frontend:
	cd frontend && npm install

dev-api:
	uv run --directory backend uvicorn flowpilot.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	uv run --directory backend pytest -v

lint:
	uv run --directory backend ruff check src tests
	uv run --directory backend ruff format --check src tests

typecheck:
	uv run --directory backend mypy src

benchmark:
	uv run --directory backend flowpilot-benchmark --output benchmark_report.md

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
