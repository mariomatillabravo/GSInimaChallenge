# Development shortcuts. Each target is a thin wrapper around a plain command, and the README
# lists the full equivalent command for every target, so Make is a convenience, never a requirement.
# Unprefixed targets work on the backend, front-* targets on the front-end; check runs both.

BACKEND_RUN := uv run --directory backend
FRONTEND_NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help install run demo test lint format typecheck check up down \
	front-install front-dev front-test front-lint front-format front-typecheck front-build front-check

help:
	@echo "Available targets:"
	@echo "  install          Install backend dependencies from the lockfile"
	@echo "  run              Start the API with auto-reload on http://localhost:8000"
	@echo "  demo             Start the API in demo mode (recorded data, no API key needed)"
	@echo "  test             Run the backend test suite"
	@echo "  lint             Check backend linting and formatting"
	@echo "  format           Apply safe lint fixes and format the backend code"
	@echo "  typecheck        Run backend static type checking"
	@echo "  front-install    Install front-end dependencies from the lockfile"
	@echo "  front-dev        Start the front-end dev server on http://localhost:5173"
	@echo "  front-test       Run the front-end test suite"
	@echo "  front-lint       Check front-end linting and formatting"
	@echo "  front-format     Apply lint fixes and format the front-end code"
	@echo "  front-typecheck  Run front-end static type checking"
	@echo "  front-build      Build the front-end for production into frontend/dist"
	@echo "  front-check      Run front-lint, front-typecheck, front-test and front-build"
	@echo "  check            Run every backend and front-end check (what CI runs)"
	@echo "  up               Build and start the Docker stack (demo mode by default)"
	@echo "  down             Stop the Docker stack"

install:
	uv sync --locked --directory backend

run:
	$(BACKEND_RUN) uvicorn app.main:create_app --factory --reload

demo:
	DEMO_MODE=true $(BACKEND_RUN) uvicorn app.main:create_app --factory --reload

test:
	$(BACKEND_RUN) pytest

lint:
	$(BACKEND_RUN) ruff check .
	$(BACKEND_RUN) ruff format --check .

format:
	$(BACKEND_RUN) ruff check --fix --exit-zero .
	$(BACKEND_RUN) ruff format .

typecheck:
	$(BACKEND_RUN) mypy

front-install:
	$(FRONTEND_NPM) ci

front-dev:
	$(FRONTEND_NPM) run dev

front-test:
	$(FRONTEND_NPM) test

front-lint:
	$(FRONTEND_NPM) run lint

front-format:
	$(FRONTEND_NPM) run format

front-typecheck:
	$(FRONTEND_NPM) run typecheck

front-build:
	$(FRONTEND_NPM) run build

front-check: front-lint front-typecheck front-test front-build

check: lint typecheck test front-check

up:
	docker compose up --build

down:
	docker compose down
