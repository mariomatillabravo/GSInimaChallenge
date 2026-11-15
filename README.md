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

### How the service reads AEMET

- A requested range is split into **calendar months in UTC**, the longest range AEMET accepts per request.
- Each month follows AEMET's two-step protocol, and the outcome is read from the `estado` field of the envelope.
  "No data" is a valid empty result, not an error.
- Transient failures (network errors, timeouts, rate limiting, HTTP 5xx) are **retried with exponential
  backoff**. A rejected API key is not retried.
- Persistent failures are classified so the API can report them as **503** (unreachable or rate limited),
  **504** (timeout) or **502** (any other upstream failure).

### Data cleaning

Every record goes through the same rule, both for live responses and for recorded ones:

| Situation | Treatment |
|---|---|
| A value is `"NaN"`, `null`, non-numeric or absent | That value is missing |
| The record is flagged as bad quality (`qdato = 1`) | All its values are missing |
| No value is left, or the timestamp is invalid | The record is discarded |
| Records arrive unsorted or repeated | They are sorted by time; a repeated timestamp keeps the last record |

The design is explained in [ADR-0004](docs/adr/0004-aemet-client.md).

## Time zone handling

| Where | Time zone |
|---|---|
| Input datetimes without an offset | `Europe/Madrid` by default, or the zone given in `tz` |
| Inside the service | UTC, with timezone-aware datetimes only |
| Output datetimes | `Europe/Madrid`, always including the UTC offset |
| Station days and months (daily and monthly aggregation) | Station local time, a fixed `UTC-03:00` |

### Input

- Datetimes use the format `YYYY-MM-DDTHH:MM:SS`, for example `2026-01-15T00:00:00`.
- Their zone can be given with `tz`, as an IANA name (`Europe/Berlin`) or as an offset (`+02:00`). Without `tz`,
  they are interpreted in `Europe/Madrid`: the users are in Spain and the output is in Madrid time, so asking for
  data "from 00:00" returns data from 00:00.
- A datetime may also carry its own offset (`2026-01-15T00:00:00+02:00`) or `Z` for UTC. Giving `tz` as well is
  rejected as a conflict.
- Both ends of the range are **inclusive**, as in the AEMET API.
- Every response states how the input was interpreted, for example `"Europe/Madrid (default)"`.
- In a URL, `+` must be written as `%2B` (`tz=%2B02:00`), because a literal `+` in a query string means a space.
  An offset that arrives as ` 02:00` can only mean `+02:00`, so it is accepted as such.

### Daylight saving time

Europe/Madrid changes its offset twice a year, and two kinds of local times do not map to exactly one instant:

| Change | What happens | Example | Result |
|---|---|---|---|
| Spring forward (last Sunday of March) | At 02:00 the clocks jump to 03:00 | `2026-03-29T02:30:00` does not exist | HTTP 422 |
| Fall back (last Sunday of October) | At 03:00 the clocks go back to 02:00 | `2026-10-25T02:30:00` happens twice | HTTP 422 naming both offsets |

The API never guesses: an explicit offset always selects a single instant (`2026-10-25T02:30:00` with
`tz=%2B02:00` is `00:30Z`, with `tz=%2B01:00` it is `01:30Z`). Python itself would silently pick one
interpretation, so these cases are detected explicitly.

On output, offsets switch exactly at the change and no timestamp is duplicated or lost. On the fall-back day the
repeated hour appears twice, each time with its own offset:

| Instant (UTC) | Output (Europe/Madrid) |
|---|---|
| `2026-10-25T00:30:00Z` | `2026-10-25T02:30:00+02:00` |
| `2026-10-25T01:30:00Z` | `2026-10-25T02:30:00+01:00` |

Clients should therefore compare and sort by the full datetime with its offset, never by the local wall-clock
text. The DST test suite lives in [`test_dst_input.py`](backend/tests/unit/test_dst_input.py) and
[`test_dst_output.py`](backend/tests/unit/test_dst_output.py), and property-based tests check that every other
instant survives the round trip to Madrid time and back.

### Station local time

Daily and monthly aggregation cut days and months in the stations' local time, a fixed `UTC-03:00`. The bases
operate seasonally (November to March) in a region that uses UTC−03:00 all year round, and a fixed offset keeps
every station day exactly 24 hours long. The full reasoning, including the rejected `America/Punta_Arenas`, is in
[ADR-0002](docs/adr/0002-time-zone-strategy.md).

## Aggregation

| `aggregation` | Rows | Value of each measurement |
|---|---|---|
| `none` | The original ten-minute observations | As published by AEMET |
| `hourly` | One per clock hour | Mean of the hour |
| `daily` | One per **station-local day** (00:00 to 24:00 at UTC−03:00) | Mean of the day |
| `monthly` | One per **station-local month** | Mean of the month |

- Each row is labelled with the start of its bucket, written in Europe/Madrid with its offset. A station day
  starts at 04:00 (winter) or 05:00 (summer) Madrid time, so daily and monthly rows also carry a readable
  `period` in station time, such as `"2026-03-29"` or `"2026-03"`.
- Means ignore missing values. A measurement missing in the whole bucket is `null`.
- Only observations with at least one of the requested measurements are used, and, without aggregation, only
  those are returned.

### Data quality fields

Every aggregated row says how much data it is based on, so an incomplete bucket is never mistaken for a complete
one:

| Field | Meaning |
|---|---|
| `samples` | Observations used: those with at least one requested value |
| `expected_samples` | Ten-minute slots in a complete bucket: 6 per hour, 144 per day, days × 144 per month |
| `coverage` | `samples / expected_samples` as a percentage |

Every bucket between the start and the end of the range is returned, **including empty ones** (`samples = 0`), so
gaps stay visible. A bucket cut by the requested range (for example, a day requested from 15:00 station time)
honestly reports its partial coverage, because its mean is not comparable to that of a full bucket. Station days
are always 24 hours long, so Madrid's DST never makes a bucket look incomplete.

The reasoning, including the rejected Madrid-day and UTC-day alternatives, is in
[ADR-0005](docs/adr/0005-aggregation.md).

## Design decisions

Each significant decision is recorded as an Architecture Decision Record (ADR) in [`docs/adr/`](docs/adr/), with
its context, the options considered and its consequences.

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-web-framework.md) | FastAPI as the web framework: typed validation, generated OpenAPI docs and dependency injection that makes the AEMET client easy to replace in tests and demo mode |
| [0002](docs/adr/0002-time-zone-strategy.md) | UTC inside the service, Europe/Madrid as default input and as output zone, fixed `UTC-03:00` for station days, inclusive ranges |
| [0003](docs/adr/0003-dst-input-policy.md) | Non-existent and ambiguous local times are rejected with HTTP 422 instead of being guessed |
| [0004](docs/adr/0004-aemet-client.md) | A `WeatherSource` port with an AEMET client and a recorded source sharing one pure parser; monthly windows, retries, data cleaning and upstream error classification |
| [0005](docs/adr/0005-aggregation.md) | Buckets in station local time labelled in Madrid time, means of non-missing values, and `samples`, `expected_samples` and `coverage` on every aggregated row, empty buckets included |

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
| `AEMET_BASE_URL` | `https://opendata.aemet.es/opendata` | AEMET OpenData base URL |
| `AEMET_TIMEOUT_SECONDS` | `30` | Timeout of each HTTP request to AEMET |
| `AEMET_MAX_ATTEMPTS` | `3` | Attempts per monthly window when AEMET fails transiently |
| `MAX_RANGE_DAYS_NONE` | `31` | Longest range accepted without aggregation (about 4,500 ten-minute records) |
| `MAX_RANGE_DAYS_HOURLY` | `366` | Longest range accepted with hourly aggregation |
| `MAX_RANGE_DAYS_DAILY` | `3660` | Longest range accepted with daily aggregation (ten years) |
| `MAX_RANGE_DAYS_MONTHLY` | none | Longest range accepted with monthly aggregation (unlimited by default) |

`DEMO_MODE` defaults to `false` on purpose: a deployment that forgets its API key refuses to start with a clear
message, instead of silently serving demo data. The API key is held as a secret value that is never printed or
logged.

The range limits keep every response bounded in size. A longer request is rejected with HTTP 422 and a message
suggesting a shorter range or a coarser aggregation, instead of being paginated.

### Commands

Run them from the repository root.

| Make target | Equivalent command | Purpose |
|---|---|---|
| `make install` | `uv sync --locked --directory backend` | Install backend dependencies exactly as pinned in `uv.lock` |
| `make run` | `uv run --directory backend uvicorn app.main:create_app --factory --reload` | Start the API with auto-reload on <http://localhost:8000> (interactive docs at `/docs`) |
| `make test` | `uv run --directory backend pytest` | Run the backend test suite |
| `make lint` | `uv run --directory backend ruff check .`<br>`uv run --directory backend ruff format --check .` | Check linting and formatting without changing files |
| `make format` | `uv run --directory backend ruff check --fix --exit-zero .`<br>`uv run --directory backend ruff format .` | Apply safe lint fixes, then format the code (remaining lint issues are reported by `make lint`) |
| `make typecheck` | `uv run --directory backend mypy` | Static type checking in strict mode |
| `make check` | The `lint`, `typecheck` and `test` commands above | Everything CI runs |
