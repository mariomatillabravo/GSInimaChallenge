# Development shortcuts. Each target is a thin wrapper around a plain command, and the README
# lists the full equivalent command for every target, so Make is a convenience, never a requirement.

BACKEND_RUN := uv run --directory backend

.DEFAULT_GOAL := help
.PHONY: help install run test lint format typecheck check

help:
	@echo "Available targets:"
	@echo "  install    Install backend dependencies from the lockfile"
	@echo "  run        Start the API with auto-reload on http://localhost:8000"
	@echo "  test       Run the backend test suite"
	@echo "  lint       Check linting and formatting"
	@echo "  format     Apply safe lint fixes and format the code"
	@echo "  typecheck  Run static type checking"
	@echo "  check      Run lint, typecheck and test (what CI runs)"

install:
	uv sync --locked --directory backend

run:
	$(BACKEND_RUN) uvicorn app.main:create_app --factory --reload

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

check: lint typecheck test
