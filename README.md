# AEMET Antarctica Weather API

[![CI](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml/badge.svg)](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml)

Web API that retrieves, caches and aggregates weather data from the Spanish Antarctic stations
(Juan Carlos I and Gabriel de Castilla) published by
[AEMET OpenData](https://opendata.aemet.es/centrodedescargas/inicio).

## Data source

All weather data comes from the AEMET OpenData API (Spanish State Meteorological Agency), Antarctica endpoint, for
two automatic weather stations:

| Station | Location | AEMET identifier |
|---|---|---|
| Juan Carlos I | Livingston Island, South Shetland Islands | `89064` |
| Gabriel de Castilla | Deception Island, South Shetland Islands | `89070` |

> © AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma.
>
> *(© AEMET. Use and reproduction of the information is authorised provided AEMET is cited as its author.)*
> See AEMET's [legal notice](https://www.aemet.es/es/nota_legal).

The upstream behaviour the service relies on (two-step responses, errors reported in the body, one-month maximum
range, `"NaN"` for missing values, data availability) was verified against the real API and is documented in
[docs/aemet-api.md](docs/aemet-api.md). A few real responses are included as test fixtures; their origin is
documented in [`backend/tests/fixtures/aemet/`](backend/tests/fixtures/aemet/README.md).

## Design decisions

Each significant decision is recorded as an Architecture Decision Record (ADR) in [`docs/adr/`](docs/adr/), with
its context, the options considered and its consequences.

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-web-framework.md) | FastAPI as the web framework: typed validation, generated OpenAPI docs and dependency injection that makes the AEMET client easy to replace in tests and demo mode |

## Development

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- GNU Make (optional). Every target is a shortcut for the plain command listed below.
  On Windows it can be installed with `winget install ezwinports.make`.

### Configuration

The backend reads its configuration from environment variables or from a `backend/.env` file, which is
git-ignored. To start, copy [`backend/.env.example`](backend/.env.example) to `backend/.env`.

| Variable | Default | Description |
|---|---|---|
| `DEMO_MODE` | `false` | Serve recorded AEMET responses instead of calling the real API. No API key is needed. |
| `AEMET_API_KEY` | none | Personal AEMET OpenData API key. Required when `DEMO_MODE` is `false`. |

`DEMO_MODE` defaults to `false` on purpose: a deployment that forgets its API key refuses to start with a clear
message, instead of silently serving demo data. The API key is held as a secret value that is never printed or
logged.

### Commands

Run them from the repository root.

| Make target | Equivalent command | Purpose |
|---|---|---|
| `make install` | `uv sync --locked --directory backend` | Install backend dependencies exactly as pinned in `uv.lock` |
| `make run` | `uv run --directory backend uvicorn app.main:create_app --factory --reload` | Start the API with auto-reload on <http://localhost:8000> (interactive docs at `/docs`) |
| `make test` | `uv run --directory backend pytest` | Run the backend test suite |
| `make lint` | `uv run --directory backend ruff check .`<br>`uv run --directory backend ruff format --check .` | Check linting and formatting without changing files |
| `make format` | `uv run --directory backend ruff check --fix .`<br>`uv run --directory backend ruff format .` | Apply safe lint fixes, then format the code |
| `make typecheck` | `uv run --directory backend mypy` | Static type checking in strict mode |
| `make check` | The `lint`, `typecheck` and `test` commands above | Everything CI runs |
