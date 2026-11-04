.PHONY: help setup dev lint format test integration type check clean build up down logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Development (uv: https://docs.astral.sh/uv/)
# ---------------------------------------------------------------------------

setup: ## Create .venv with Python 3.15 and the locked dev dependencies
	uv sync

# wg-quick needs root. Inside the Dev Container that is safe: it has its own network namespace.
# Anywhere else, root would change the host's WireGuard, so make dev refuses to run.
dev: ## Run with hot reload and real WireGuard (in the Dev Container)
	@test -n "$$DEVCONTAINER" || { echo "make dev needs the Dev Container: see CONTRIBUTING.md"; exit 1; }
	@echo "API: http://127.0.0.1:8000/api/v1/docs  (X-API-Key: $$API_KEY)"
	uv sync --quiet
	sudo --preserve-env=API_KEY,LOG_LEVEL,UV_PROJECT_ENVIRONMENT env PYTHONDONTWRITEBYTECODE=1 \
		uv run --no-sync uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

lint: ## Run linter and format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format code
	uv run ruff format .

test: ## Run unit tests with coverage
	uv run pytest

integration: ## Run integration tests against the Docker image and real WireGuard (needs the wireguard module)
	docker build -t wg-agent:integration .
	uv run tests/integration/run.sh wg-agent:integration

type: ## Run type checker
	uv run ty check

check: lint type test ## Run all checks (lint + type + test)

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

build: ## Build Docker image
	docker compose build

up: ## Start container (build + detach)
	docker compose up -d --build

down: ## Stop container
	docker compose down

logs: ## Follow container logs
	docker compose logs -f wg-agent
