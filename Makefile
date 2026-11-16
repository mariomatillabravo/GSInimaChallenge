# Development shortcuts. Each target is a thin wrapper around a plain command, and the README
# lists the full equivalent command for every target, so Make is a convenience, never a requirement.
# Unprefixed targets work on the backend, front-* targets on the front-end; check runs both.

BACKEND_RUN := uv run --directory backend
FRONTEND_NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help install run demo test coverage lint format typecheck openapi-check api-types check up down \
	front-install front-dev front-test front-coverage front-lint front-format front-typecheck front-types-check \
	front-build front-check

help:
	@echo "Available targets:"
	@echo "  install           Install backend dependencies from the lockfile"
	@echo "  run               Start the API with auto-reload on http://localhost:8000"
	@echo "  demo              Start the API in demo mode (recorded data, no API key needed)"
	@echo "  test              Run the backend test suite"
	@echo "  coverage          Run the backend tests with coverage (fails below 95 %), HTML in backend/htmlcov"
	@echo "  lint              Check backend linting and formatting"
	@echo "  format            Apply safe lint fixes and format the backend code"
	@echo "  typecheck         Run backend static type checking"
	@echo "  openapi-check     Check that frontend/openapi.json matches the API"
	@echo "  api-types         Regenerate frontend/openapi.json and the front-end API types"
	@echo "  front-install     Install front-end dependencies from the lockfile"
	@echo "  front-dev         Start the front-end dev server on http://localhost:5173"
	@echo "  front-test        Run the front-end test suite"
	@echo "  front-coverage    Run the front-end tests with a coverage report, HTML in frontend/coverage"
	@echo "  front-lint        Check front-end linting and formatting"
	@echo "  front-format      Apply lint fixes and format the front-end code"
	@echo "  front-typecheck   Run front-end static type checking"
	@echo "  front-types-check Check that the API types match frontend/openapi.json"
	@echo "  front-build       Build the front-end for production into frontend/dist"
	@echo "  front-check       Run every front-end check, then the production build"
	@echo "  check             Run every backend and front-end check (what CI runs)"
	@echo "  up                Build and start the Docker stack: web on :8080, API on :8000 (demo mode)"
	@echo "  down              Stop the Docker stack"

install:
	uv sync --locked --directory backend

run:
	$(BACKEND_RUN) uvicorn app.main:create_app --factory --reload

# Make exports the variable itself: the `VAR=value command` form only works in POSIX shells, and
# GNU Make on Windows runs recipes with cmd.exe when no sh is on the PATH.
demo: export DEMO_MODE = true
demo:
	$(BACKEND_RUN) uvicorn app.main:create_app --factory --reload

test:
	$(BACKEND_RUN) pytest

coverage:
	$(BACKEND_RUN) pytest --cov --cov-report=term-missing --cov-report=html

lint:
	$(BACKEND_RUN) ruff check .
	$(BACKEND_RUN) ruff format --check .

format:
	$(BACKEND_RUN) ruff check --fix --exit-zero .
	$(BACKEND_RUN) ruff format .

typecheck:
	$(BACKEND_RUN) mypy

# The front-end types are generated from frontend/openapi.json, which is exported from the API.
# Both files are committed; the *-check targets fail when one of them is out of date.
openapi-check:
	$(BACKEND_RUN) python -m scripts.export_openapi --check

api-types:
	$(BACKEND_RUN) python -m scripts.export_openapi
	$(FRONTEND_NPM) run generate:api

front-install:
	$(FRONTEND_NPM) ci

front-dev:
	$(FRONTEND_NPM) run dev

front-test:
	$(FRONTEND_NPM) test

front-coverage:
	$(FRONTEND_NPM) run coverage

front-lint:
	$(FRONTEND_NPM) run lint

front-format:
	$(FRONTEND_NPM) run format

front-typecheck:
	$(FRONTEND_NPM) run typecheck

front-types-check:
	$(FRONTEND_NPM) run check:api

front-build:
	$(FRONTEND_NPM) run build

front-check: front-lint front-typecheck front-types-check front-test front-build

check: lint typecheck openapi-check test front-check

up:
	docker compose up --build

down:
	docker compose down
