# AEMET Antarctica Weather API

[![CI](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml/badge.svg)](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml)

Web API that retrieves, caches and aggregates weather data from the Spanish Antarctic stations
(Juan Carlos I and Gabriel de Castilla) published by
[AEMET OpenData](https://opendata.aemet.es/centrodedescargas/inicio).

## API

Interactive documentation is served at `/docs` (Swagger UI) and `/redoc` once the API is running.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /api/v1/stations` | Stations that can be queried, with their AEMET identifiers and local time |
| `GET /api/v1/stations/{station_id}/measurements` | Time series of a station, optionally aggregated |

Responses larger than 1 KB are gzip-compressed when the client accepts it: one day of raw data (145 rows) goes
from 18.5 KB to 1.5 KB.

### Measurement parameters

| Parameter | Required | Description |
|---|---|---|
| `station_id` (path) | yes | `juan-carlos-i` or `gabriel-de-castilla` |
| `start`, `end` | yes | Inclusive range, `YYYY-MM-DDTHH:MM:SS`, optionally with `Z` or an offset (`%2B02:00` in a URL) |
| `tz` | no | Zone of `start`/`end` without offset: IANA name (`Europe/Berlin`) or offset. Default `Europe/Madrid` |
| `aggregation` | no | `none` (default), `hourly`, `daily` or `monthly` |
| `types` | no | `temperature`, `pressure`, `speed`, comma-separated or repeated. Default: all |
| `format` | no | `json` (default) or `csv` |

### Example

```bash
curl "http://localhost:8000/api/v1/stations/juan-carlos-i/measurements?start=2026-01-15T00:00:00&end=2026-01-16T03:00:00&aggregation=daily&types=temperature,speed"
```

```json
{
  "metadata": {
    "station": {"id": "juan-carlos-i", "name": "Juan Carlos I", "aemet_id": "89064", "aemet_name": "JCI Estacion meteorologica"},
    "aggregation": "daily",
    "start": "2026-01-15T00:00:00+01:00",
    "end": "2026-01-16T03:00:00+01:00",
    "input_interpretation": "Europe/Madrid (default)",
    "output_timezone": "Europe/Madrid",
    "station_timezone": "UTC-03:00",
    "source": "aemet",
    "count": 2
  },
  "fields": {
    "station": {"label": "Station", "unit": null},
    "datetime": {"label": "Datetime", "unit": null},
    "period": {"label": "Period", "unit": null},
    "temperature_c": {"label": "Temperature (°C)", "unit": "°C"},
    "speed_ms": {"label": "Speed (m/s)", "unit": "m/s"},
    "samples": {"label": "Samples", "unit": null},
    "expected_samples": {"label": "Expected samples", "unit": null},
    "coverage": {"label": "Coverage (%)", "unit": "%"}
  },
  "data": [
    {"station": "Juan Carlos I", "datetime": "2026-01-14T04:00:00+01:00", "period": "2026-01-14", "temperature_c": 1.91, "speed_ms": 2.09, "samples": 18, "expected_samples": 144, "coverage": 12.5},
    {"station": "Juan Carlos I", "datetime": "2026-01-15T04:00:00+01:00", "period": "2026-01-15", "temperature_c": 2.93, "speed_ms": 2.09, "samples": 127, "expected_samples": 144, "coverage": 88.2}
  ]
}
```

The example shows station-local days at work. Midnight in Madrid is 20:00 of the previous day at the station, so
the requested range touches two station days. The first one only contributes its last three hours, which its
`coverage` makes obvious.

### Field names

JSON keys are snake_case (`temperature_c`, `pressure_hpa`, `speed_ms`), which every client can use directly. The
official dataset names required by the challenge (`Station`, `Datetime`, `Temperature (°C)`, `Pressure (hPa)`,
`Speed (m/s)`) are given for every key in the `fields` block. The statement writes `ºC` (the ordinal indicator,
not the degree sign) and `hpa`, copying AEMET's metadata; the correct symbols are used instead. A requested
measurement without data is `null`; a measurement that was not requested is absent. See
[ADR-0006](docs/adr/0006-output-field-names.md).

### CSV export

`format=csv` returns the same dataset as a downloadable CSV file whose column headers are the official labels.
The example request above with `&format=csv` downloads `juan-carlos-i_daily_2026-01-15_2026-01-16.csv`:

```csv
Station,Datetime,Period,Temperature (°C),Speed (m/s),Samples,Expected samples,Coverage (%)
Juan Carlos I,2026-01-14T04:00:00+01:00,2026-01-14,1.91,2.09,18,144,12.5
Juan Carlos I,2026-01-15T04:00:00+01:00,2026-01-15,2.93,2.09,127,144,88.2
```

The CSV is built from the JSON response itself, so both formats always contain the same columns and values.
Missing values are empty cells. The file is UTF-8 with a byte order mark, so that Excel on Windows shows the
degree sign correctly.

### Errors

Every error has the same shape, and the HTTP status tells whether the problem is in the request or upstream:

```json
{"error": {"code": "invalid_parameter", "message": "'2026-10-25T02:30:00' is ambiguous in Europe/Madrid: ...", "parameter": "start"}}
```

| Status | `code` | When |
|---|---|---|
| 422 | `invalid_parameter` | Malformed or inconsistent parameter, non-existent or ambiguous local time, range too long |
| 404 | `not_found` | Unknown station (the message lists the valid ones) |
| 502 | `upstream_error` | AEMET failed, rejected the API key or answered unexpectedly |
| 503 | `upstream_unavailable` | AEMET is unreachable or rate limiting, even after retrying |
| 504 | `upstream_timeout` | AEMET did not answer in time, even after retrying |
| 500 | `internal_error` | Unexpected error; details stay in the server logs |

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
text.

Aggregated output behaves consistently:

| Aggregation | Around spring forward (2026-03-29) | Around fall back (2026-10-25) |
|---|---|---|
| Hourly | `01:00+01:00` is followed by `03:00+02:00`: there is no 02:00 row, and no data is lost | `02:00+02:00` and `02:00+01:00` are two different rows, six samples each |
| Daily | Station days stay 144 slots long; their labels move from `04:00+01:00` to `05:00+02:00` | Station days stay 144 slots long (not 25 hours); labels move from `05:00+02:00` to `04:00+01:00` |

The DST test suite lives in [`test_dst_input.py`](backend/tests/unit/test_dst_input.py),
[`test_dst_output.py`](backend/tests/unit/test_dst_output.py) and
[`test_dst_aggregation.py`](backend/tests/unit/test_dst_aggregation.py), and property-based tests check that every
other instant survives the round trip to Madrid time and back.

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
| [0006](docs/adr/0006-output-field-names.md) | snake_case JSON keys with a `fields` block holding the official labels, corrected unit symbols, readable station names |
| [0007](docs/adr/0007-concurrency-model.md) | Synchronous request handling: SQLite and pandas block, so `def` endpoints in the thread pool are correct by construction |

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
| `DEMO_DATA_DIR` | `sample_data/demo` | Folder with the recorded responses used in demo mode, relative to `backend/` |
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
