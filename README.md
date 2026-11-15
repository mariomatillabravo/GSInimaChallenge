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

The repository includes a few real AEMET responses as test fixtures; their origin is documented in
[`backend/tests/fixtures/aemet/`](backend/tests/fixtures/aemet/README.md).

## Development

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- GNU Make (optional). Every target is a shortcut for the plain command listed below.
  On Windows it can be installed with `winget install ezwinports.make`.

### Commands

Run them from the repository root.

| Make target | Equivalent command | Purpose |
|---|---|---|
| `make install` | `uv sync --locked --directory backend` | Install backend dependencies exactly as pinned in `uv.lock` |
| `make run` | `uv run --directory backend uvicorn app.main:app --reload` | Start the API with auto-reload on <http://localhost:8000> (interactive docs at `/docs`) |
| `make test` | `uv run --directory backend pytest` | Run the backend test suite |
| `make lint` | `uv run --directory backend ruff check .`<br>`uv run --directory backend ruff format --check .` | Check linting and formatting without changing files |
| `make format` | `uv run --directory backend ruff check --fix .`<br>`uv run --directory backend ruff format .` | Apply safe lint fixes, then format the code |
| `make typecheck` | `uv run --directory backend mypy` | Static type checking in strict mode |
| `make check` | The `lint`, `typecheck` and `test` commands above | Everything CI runs |
