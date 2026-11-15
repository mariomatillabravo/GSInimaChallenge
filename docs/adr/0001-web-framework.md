# ADR-0001: FastAPI as the web framework

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

The service is a Python web API that validates several query parameters (datetimes, time zones, enumerations),
returns structured JSON and CSV, and must be easy to test with the upstream AEMET API replaced by fakes. The
challenge allows FastAPI or Flask. A TypeScript front-end will consume the API, so a machine-readable API
description is valuable.

## Options considered

1. **FastAPI**: request validation and serialization through Pydantic models and type hints; OpenAPI schema and
   interactive docs generated automatically; built-in dependency injection (`Depends`) that tests can override.
   Younger ecosystem than Flask, and tied to the release cadence of Starlette and Pydantic.
2. **Flask**: very mature and simple. Validation, serialization and OpenAPI require extensions
   (e.g. marshmallow and flask-smorest) and more glue code; no built-in dependency injection.
3. **Django REST Framework**: complete, but brings an ORM, settings system and project structure that this small,
   database-light service does not need.

## Decision

Use **FastAPI**. Typed request/response models give validation and clear 422 errors for free, the generated
OpenAPI schema documents the API for evaluators and lets the front-end generate its TypeScript types, and
`Depends` makes swapping the AEMET client for a recorded or fake source (demo mode, tests) a one-line override.

## Consequences

- Endpoints, schemas and errors are described once, in Python types, and appear automatically at `/docs`.
- The concurrency model (synchronous or asynchronous endpoints) is a separate decision, recorded in its own ADR.
- Upgrades follow Starlette and Pydantic. For example, Starlette's `TestClient` now prefers `httpx2` over `httpx`,
  so `httpx2` is a development-only dependency while application code keeps using `httpx`.
