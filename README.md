# AEMET Antarctica Weather API

[![CI](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml/badge.svg)](https://github.com/mariomatillabravo/GSInimaChallenge/actions/workflows/ci.yml)

Web API that retrieves, caches and aggregates weather data from the Spanish Antarctic stations
(Juan Carlos I and Gabriel de Castilla) published by
[AEMET OpenData](https://opendata.aemet.es/centrodedescargas/inicio), with a web app to query and chart it.

![The web app in demo mode: hourly means of Juan Carlos I across the change to summer time on 30 March 2025, as
charts of temperature, pressure and wind speed above the table of rows](docs/images/web-app.png)

**Contents**

- [Quickstart](#quickstart): run it in one minute, without an API key
- [Architecture](#architecture): components, the life of a request, where the code lives
- [API](#api): endpoints, parameters, CSV export, wind-energy metrics, errors
- [Data source](#data-source): AEMET OpenData and how its data is cleaned
- [Time zone handling](#time-zone-handling): Madrid input and output, daylight saving time, station time
- [Aggregation](#aggregation): station-local buckets and data quality fields
- [Cache](#cache): freshness, behaviour when AEMET fails, storage
- [Logging](#logging): request IDs, text and JSON lines
- [Limits and scaling](#limits-and-scaling): known limits and how the service would grow
- [Front-end](#front-end): the web app, its form, charts and table
- [Limitations and next steps](#limitations-and-next-steps)
- [Design decisions](#design-decisions): the architecture decision records
- [Development](#development): prerequisites, configuration, tests, commands
- [Project status](#project-status)

## Quickstart

### Run it in one minute, without an API key

The repository includes one month of real AEMET data (March 2025, both stations), so the whole API runs in
**demo mode** without an AEMET account.

With Docker:

```bash
git clone https://github.com/mariomatillabravo/GSInimaChallenge.git
cd GSInimaChallenge
docker compose up --build
```

Or with Python 3.12 and [uv](https://docs.astral.sh/uv/) (see [Commands](#commands) for the commands without Make):

```bash
make install
make demo
```

With Docker, the web app is at <http://localhost:8080> (with Python, see [Front-end](#front-end) to run it). Then
open the interactive documentation at <http://localhost:8000/docs>, or look at the Madrid spring DST change of 2025
hour by hour:

```bash
curl "http://localhost:8000/api/v1/stations/juan-carlos-i/measurements?start=2025-03-30T00:00:00&end=2025-03-30T06:00:00&aggregation=hourly&types=temperature"
```

| `datetime` | `temperature_c` | `samples` |
|---|---|---|
| `2025-03-30T00:00:00+01:00` | 0.63 | 6 |
| `2025-03-30T01:00:00+01:00` | 0.68 | 6 |
| `2025-03-30T03:00:00+02:00` | 0.48 | 6 |
| `2025-03-30T04:00:00+02:00` | 0.23 | 6 |
| `2025-03-30T05:00:00+02:00` | 0.55 | 6 |
| `2025-03-30T06:00:00+02:00` | 0.9 | 1 |

The rows jump from 01:00 to 03:00 because 02:00 does not exist in Madrid that day, and no observation is lost.
The last row has a single sample because the end of the range (06:00) is inclusive. Outside March 2025 the demo
returns an empty result with a notice; `GET /api/v1/stations` shows the exact recorded range.

### Use real AEMET data

1. Request a free API key at <https://opendata.aemet.es/centrodedescargas/inicio>, preferably with a personal
   e-mail address.
2. Copy `backend/.env.example` to `backend/.env` and set `DEMO_MODE=false` and `AEMET_API_KEY=<your key>`.
3. Run `make run`, or with Docker `DEMO_MODE=false docker compose up --build`
   (PowerShell: `$env:DEMO_MODE="false"; docker compose up --build`).

## Architecture

```mermaid
flowchart LR
    browser["Browser"] -->|"page and /api/..."| web["nginx in Docker (:8080)<br/>or the Vite dev server"]
    web -->|"/api/..."| api
    scripts["curl, scripts"] --> api
    subgraph backend ["Backend: Python, FastAPI, synchronous"]
        api["API routes (:8000)"] --> service["MeasurementService<br/>cache-first by UTC month"]
        service --> repository["CacheRepository"]
        repository --> sqlite[("SQLite cache<br/>WAL")]
        service --> source["WeatherSource"]
        source --> aemetclient["AEMET client"]
        source --> recorded["Recorded source<br/>(demo mode)"]
    end
    aemetclient -->|"HTTPS, two steps per month"| aemet["AEMET OpenData"]
    recorded --> files[("Recorded AEMET responses<br/>March 2025")]
```

The browser only talks to the origin that served the page: nginx (or the Vite dev server) serves the web app and
forwards `/api/...` to the API, so no CORS is needed. Behind the API, one service reads every range from the SQLite
cache, fetching first the months that are missing or expired. It reaches the data through a `WeatherSource`
interface with two implementations, the AEMET client and the recorded source of demo mode, which share the same
parser, so demo mode runs the real code path.

The life of a request for measurements:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as API route
    participant S as MeasurementService
    participant DB as SQLite cache
    participant W as WeatherSource
    C->>A: GET measurements (start, end, aggregation, types)
    A->>A: Interpret the times in Madrid, reject DST gaps and overlaps, check the range
    A->>S: Query
    S->>DB: Which months of the range are cached, and when were they fetched?
    loop Each month that is missing or expired
        alt AEMET answers (one fetch per month, shared by concurrent requests)
            S->>W: Fetch the month
            W-->>S: Cleaned observations
            S->>DB: Replace the whole month
        else AEMET fails or is cooling down, and the month has a copy
            S->>S: Serve the old copy, marked as stale
        else AEMET fails or is cooling down, and the month has no copy
            S-->>A: Upstream error
            A-->>C: 502, 503 with Retry-After, or 504
        end
    end
    S->>DB: Read the whole range
    S->>S: Aggregate in station-local buckets, add wind-energy metrics if asked
    S-->>A: Rows and cache report
    A-->>C: JSON or CSV with X-Cache-Status, X-Data-Stale and X-Request-ID
```

Where the code lives:

| Path | What it holds |
|---|---|
| [`backend/app/main.py`](backend/app/main.py) | Application factory: settings, logging, database and dependency wiring |
| [`backend/app/api/`](backend/app/api/) | Routes, response schemas, presenters (JSON and CSV), error mapping, request ID middleware |
| [`backend/app/services/`](backend/app/services/) | The measurement service (cache-first reads and fetches), single flight, circuit breaker |
| [`backend/app/domain/`](backend/app/domain/) | Pure logic: time ranges and DST rules, time zones, monthly chunks, freshness, aggregation, wind-energy metrics, stations, measurement definitions |
| [`backend/app/clients/`](backend/app/clients/) | AEMET client, recorded source for demo mode, the shared parser and cleaning rule |
| [`backend/app/db/`](backend/app/db/) | SQLite engine and connection settings, schema and its version, repository |
| [`backend/app/core/`](backend/app/core/) | Configuration, exceptions, the injected clock, logging |
| [`backend/scripts/`](backend/scripts/) | OpenAPI export, demo data recording, AEMET exploration |
| [`backend/tests/`](backend/tests/) | Unit tests (pure logic, clients with mocked HTTP) and integration tests (the whole HTTP stack on real SQLite files) |
| [`frontend/src/api/`](frontend/src/api/) | Typed client, types generated from the OpenAPI document, TanStack Query hooks |
| [`frontend/src/lib/`](frontend/src/lib/) | Pure logic: form rules and ranges, table sorting and paging, chart ticks and gaps, datetime formatting |
| [`frontend/src/components/`](frontend/src/components/) | Query form, result summary, charts, table, demo banner, error display |
| [`docs/`](docs/) | Architecture decision records, notes on the AEMET API, the screenshot above |

## API

Interactive documentation is served at `/docs` (Swagger UI) and `/redoc` once the API is running.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /api/v1/meta` | Options and limits for building a query: aggregation levels with their maximum range, measurement types and wind-energy metrics with their labels and units, time zones, real or demo data |
| `GET /api/v1/stations` | Stations that can be queried, with their AEMET identifiers and local time |
| `GET /api/v1/stations/{station_id}/measurements` | Time series of a station, optionally aggregated |

`/api/v1/meta` lets a client such as the front-end read these values instead of copying them: the maximum ranges
come from the configuration (`MAX_RANGE_DAYS_*`), so a copy would silently drift when a deployment changes them.

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
| `metrics` | no | `extended` adds [wind-energy metrics](#wind-energy-metrics) to hourly, daily and monthly rows |
| `format` | no | `json` (default) or `csv` |

The values of `aggregation`, `types`, `metrics` and `format` are accepted in any letter case (`Hourly`, `CSV`);
responses always use the lower-case form.

**Maximum range.** Each aggregation level accepts a maximum range (`MAX_RANGE_DAYS_*` in
[Configuration](#configuration), also returned by `/api/v1/meta`); a longer one gets a 422 that suggests a coarser
aggregation. The length is the real time elapsed between `start` and `end`, not the difference between their
calendar dates, because the limit exists to bound the number of records. Across a daylight saving time change the
two differ by one hour. In Europe/Madrid, `2025-10-01T00:00:00` to `2025-11-01T00:00:00` lasts 31 days and 1 hour
(the clock repeats an hour) and is rejected without aggregation, while `2025-03-01T00:00:00` to
`2025-04-01T00:30:00` lasts 30 days, 23 hours and 30 minutes (the clock skips an hour) and is accepted.

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
    "cache": {"status": "miss", "last_updated": null, "stale": false},
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
    {"station": "Juan Carlos I", "datetime": "2026-01-14T04:00:00+01:00", "period": "2026-01-14", "temperature_c": 2.05, "speed_ms": 2.23, "samples": 24, "expected_samples": 144, "coverage": 16.7},
    {"station": "Juan Carlos I", "datetime": "2026-01-15T04:00:00+01:00", "period": "2026-01-15", "temperature_c": 2.91, "speed_ms": 2.08, "samples": 139, "expected_samples": 144, "coverage": 96.5}
  ]
}
```

The example shows station-local days at work. Midnight in Madrid is 20:00 of the previous day at the station, so
the requested range touches two station days. The first one only contributes its last four hours (24 of 144
samples), and the second one misses its last five samples, because the range ends at 03:00 in Madrid, an hour
before the station day does; their `coverage` makes both obvious.

`metadata.cache` tells whether the data came from the [cache](#cache): this was the first request for January
2026, so it was fetched (`miss`); repeating it gives `hit`. `last_updated` is `null` because January can no
longer change, and `stale` is `false` because nothing had to be served from an outdated copy. The same values are
sent in the `X-Cache-Status` and `X-Data-Stale` headers, also on CSV downloads.

### Empty results

A range without observations is a valid empty result (HTTP 200), and `metadata.notice` explains it:

- with real data: AEMET has no data for the range, as the stations mostly report during the austral summer
  campaigns (roughly November to March);
- in demo mode: there is no recording for the range, and the notice gives the recorded span. `GET /api/v1/stations`
  also reports each station's `available_range` in demo mode (it is `null` with real data, which cannot be known
  without extra calls to AEMET).

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
Juan Carlos I,2026-01-14T04:00:00+01:00,2026-01-14,2.05,2.23,24,144,16.7
Juan Carlos I,2026-01-15T04:00:00+01:00,2026-01-15,2.91,2.08,139,144,96.5
```

The CSV is built from the JSON response itself, so both formats always contain the same columns and values.
Missing values are empty cells. The file is UTF-8 with a byte order mark, so that Excel on Windows shows the
degree sign correctly.

### Wind-energy metrics

`metrics=extended` adds statistics for wind-energy analysis to each aggregated row, with their labels and units in
`fields`, so they also appear in the CSV export ([ADR-0016](docs/adr/0016-wind-energy-metrics.md)):

| Key | Label | Computation over the bucket | Needs |
|---|---|---|---|
| `speed_cubic_mean_ms` | Cubic mean speed (m/s) | ∛(mean of v³) | speed |
| `speed_max_ms` | Maximum 10-minute speed (m/s) | highest ten-minute mean speed | speed |
| `temperature_min_c`, `temperature_max_c` | Minimum / Maximum 10-minute temperature (°C) | lowest / highest ten-minute mean | temperature |
| `air_density_kgm3` | Air density (kg/m³) | mean of ρ = p / (R·T) per observation, dry air | temperature, pressure |
| `power_density_wm2` | Wind power density (W/m²) | mean of ½·ρ·v³ per observation | all three |

Each metric appears when the types it needs are requested; with raw ten-minute records the parameter is rejected
with a 422, since a bucket statistic of one value would repeat it. The default response does not change.

Why these and not the mean speed: the power of the wind grows with the cube of its speed, so a few windy hours
carry more energy than many calm ones. The recorded month of March 2025 at Juan Carlos I shows it (the range
starts at 04:00 in Madrid, midnight at the station, so it falls entirely in the station's month of March):

```bash
curl "http://localhost:8000/api/v1/stations/juan-carlos-i/measurements?start=2025-03-01T04:00:00&end=2025-03-31T23:59:00&aggregation=monthly&metrics=extended"
```

| `period` | `speed_ms` | `speed_cubic_mean_ms` | `speed_max_ms` | `air_density_kgm3` | `power_density_wm2` | `coverage` |
|---|---|---|---|---|---|---|
| `2025-03` | 3.1 | 4.28 | 13.4 | 1.25 | 48.8 | 99.1 |

The cubic mean is 38 % above the mean speed, and the power density, averaged observation by observation, is 2.6
times what ½·ρ·v³ of the mean speed would give (18.6 W/m²).

Limitations, all documented in the ADR:

- **Maximum speed is the highest ten-minute mean, not a gust.** AEMET also publishes the maximum within each ten
  minutes (`velx`) and temperature extremes (`tmn`, `tmx`); storing them would give real gusts and extremes.
- **Sensor height**: the stations measure at about 10 m, while turbine hubs stand at 80 to 120 m, where the wind is
  stronger. The metrics describe the site at sensor height; extrapolating needs a wind shear model and its
  parameters.
- **Dry air**: humidity changes the density by less than 0.24 % even in saturated air at 0 °C.
- **Power density is the power of the wind**, not of a turbine: energy produced also depends on its power curve.

### Errors

Every error has the same shape, and the HTTP status tells whether the problem is in the request or upstream.
Upstream errors only reach the client when a month of the range has no cached copy (see
[When AEMET fails](#when-aemet-fails)). Every response, errors included, carries an `X-Request-ID` header that
identifies its lines in the [logs](#logging):

```json
{"error": {"code": "invalid_parameter", "message": "'2026-10-25T02:30:00' is ambiguous in Europe/Madrid: ...", "parameter": "start"}}
```

| Status | `code` | When |
|---|---|---|
| 422 | `invalid_parameter` | Malformed or inconsistent parameter, non-existent or ambiguous local time, range too long |
| 404 | `not_found` | Unknown station (the message lists the valid ones) |
| 502 | `upstream_error` | AEMET failed, rejected the API key or answered unexpectedly |
| 503 | `upstream_unavailable` | AEMET is unreachable or rate limiting, even after retrying, or it failed less than `UPSTREAM_COOLDOWN_SECONDS` ago and is not being called (the `Retry-After` header says when to try again) |
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
  **504** (timeout) or **502** (any other upstream failure), unless a cached copy can be served instead.

### Data cleaning

Every record goes through the same rule, both for live responses and for recorded ones:

| Situation | Treatment |
|---|---|
| A value is `"NaN"`, `null`, non-numeric or absent | That value is missing |
| The record is flagged as bad quality (`qdato = 1`) | All its values are missing |
| No value is left, or the timestamp is invalid | The record is discarded |
| Records arrive unsorted or repeated | They are sorted by time; a repeated timestamp keeps the last record |

Each fetched month logs how many records were discarded, at `INFO` level and only when there are some, with the
counts as separate fields in JSON logs (see [Logging](#logging)): a few unusable records are normal data quality,
not a fault. In the recorded demo data for March 2025, 10 of 4,464 records are discarded for Juan Carlos I and 1
for Gabriel de Castilla. The parser only counts them, staying a pure function; the AEMET client and the recorded
source write the log line, since they know the station and the month.

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
operate seasonally (November to March), months in which even historical Chilean time was UTC−03:00, and a fixed
offset keeps every station day exactly 24 hours long. The clock actually used at the bases could not be verified. The full reasoning, including the rejected `America/Punta_Arenas`, is in
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

## Cache

The service keeps the data it fetches in a local SQLite database, so repeated queries do not call AEMET again.
Every response is served from the cache: the months of the range that are missing or expired are fetched and
stored first, then the whole range is read from the cache and aggregated.

### Freshness

Data is fetched and cached by **calendar month in UTC**. A month can still change while it is in progress and
for a while after it ends, as late observations are published:

| Situation of the cached month | What a request does |
|---|---|
| Not cached | Fetches it |
| Fetched at least `CACHE_GRACE_HOURS` (48 h) after the month ended | Uses the cache, forever: the month is **final** |
| Otherwise (month in progress, or ended recently) | Uses the cache for `CACHE_TTL_MINUTES` (60 min) after the fetch, then fetches it again |

For example, January fetched on 1 February at 10:00 UTC is not final yet. A request on 5 February finds it
expired and fetches it again; that copy is final, so on 6 February nothing is fetched.

- **Empty months are cached too**, so a month without data is not requested again once it is final.
- The **month in progress** is fetched up to the current time, and months that start in the future are not
  fetched at all: they cannot have data yet.
- The **fetch time** recorded is the moment the request started, not when the fetch finished: the data is at
  least that recent, never less.
- The 48-hour grace is an assumption: how long AEMET takes to publish late Antarctic observations is still to be
  verified, so it is configurable.
- **Concurrent requests for the same month share one fetch**: the first one fetches it, and the others wait for
  its outcome (the data, or the same error) instead of calling AEMET again. Requests for different months are
  fetched in parallel. This coordination lives in each process: with several worker processes, each may fetch
  the month once, and the stored result stays correct.

The response says how it was served: `metadata.cache.status` is `hit` (nothing had to be fetched), `miss` (every
month was fetched) or `partial`, also sent as the `X-Cache-Status` header. `metadata.cache.last_updated` is the
oldest fetch time among the months that can still change, in Madrid time, or `null` when all the requested data
is final. The full reasoning is in [ADR-0009](docs/adr/0009-caching-strategy.md).

### When AEMET fails

AEMET is retried a few times on every fetch. When a fetch still fails:

- an **expired month that has a cached copy is served from that copy**: the response is a normal 200 with
  `metadata.cache.stale: true` (and `X-Data-Stale: true`), and `last_updated` tells how old the copy is;
- a **month without a copy** makes the request fail with the error in the table above, because a range is never
  served incomplete without saying so;
- **AEMET is not called again for `UPSTREAM_COOLDOWN_SECONDS`** (60 s), a pattern known as a circuit breaker.
  Meanwhile, cached copies are served at once and months without a copy fail at once with 503 and a
  `Retry-After` header, instead of every request waiting for a new round of retries (which can take more than a
  minute when AEMET times out). After the cool-down, the next request tries AEMET again.

Final months never need AEMET, so they are always served. Requests waiting for the same failed fetch all get the
copy (or the error) together. The reasoning is in [ADR-0010](docs/adr/0010-resilience.md).

### Storage

- **One file per mode** by default: `backend/data/cache.sqlite3` for real data and
  `backend/data/cache-demo.sqlite3` for the demo, so switching modes never mixes recorded and real data. In
  Docker the files live in the `cache-data` named volume. The path can be changed with `CACHE_DB_PATH`.
- **Tables**: `measurements` (one row per station and ten-minute observation, timestamps as UTC epoch seconds),
  `fetched_chunks` (which months of which station are cached, and when they were fetched) and `cache_info` (the
  data source the file belongs to).
- **Whole months**: data is stored by calendar month in UTC, the longest range AEMET accepts per request. Storing
  a month again replaces it entirely in one transaction, so the cache never keeps records the source no longer
  publishes, and readers see either the old month or the new one, never a mix. A month without data is recorded
  as such (`row_count` 0).
- **No migrations**: everything in the cache can be fetched again. The schema version is stored in the file
  (`PRAGMA user_version`); a file written by another version of the code, or for the other data source, is
  rebuilt at startup and a warning is logged.
- **Safe under concurrency**: write-ahead logging (WAL) lets reads and a write happen at the same time, and every
  write transaction takes SQLite's write lock before it reads anything (`BEGIN IMMEDIATE`), so concurrent writers,
  in threads or in several worker processes, wait for their turn instead of failing. Tests run these races on
  real files.

Library choice, schema, transaction handling and SQLite's limits are discussed in
[ADR-0008](docs/adr/0008-cache-storage.md).

## Logging

Every log line is tagged with the **ID of the request** being served, so all the lines of one request can be
found together. Two formats, chosen with `LOG_FORMAT`:

- `text` (default, for a terminal):

  ```text
  2026-11-16T17:00:02.035Z INFO docs-example-1 app.clients.recorded: Discarded 10 of 4464 records for juan-carlos-i 2025-03: no usable value or no valid timestamp.
  2026-11-16T17:00:02.070Z INFO docs-example-1 app.services.measurements: Fetched juan-carlos-i 2025-03 from demo: 4454 observations.
  2026-11-16T17:00:02.080Z INFO docs-example-1 app.access: GET /api/v1/stations/juan-carlos-i/measurements?start=2025-03-30T00:00:00&end=2025-03-30T06:00:00&aggregation=hourly 200 95.4 ms
  ```

- `json` (used by Docker Compose): one JSON object per line, ready for a log platform, with the details of
  each event as separate fields:

  ```json
  {"time": "2026-11-16T17:00:08.226Z", "level": "INFO", "logger": "app.clients.recorded", "message": "Discarded 10 of 4464 records for juan-carlos-i 2025-03: no usable value or no valid timestamp.", "request_id": "docs-example-1", "station": "juan-carlos-i", "month": "2025-03", "records": 4464, "discarded": 10}
  {"time": "2026-11-16T17:00:08.276Z", "level": "INFO", "logger": "app.access", "message": "GET /api/v1/stations/juan-carlos-i/measurements?start=2025-03-30T00:00:00&end=2025-03-30T06:00:00&aggregation=hourly 200 107.0 ms", "request_id": "docs-example-1", "http": {"method": "GET", "path": "/api/v1/stations/juan-carlos-i/measurements", "query": "start=2025-03-30T00:00:00&end=2025-03-30T06:00:00&aggregation=hourly", "status": 200, "duration_ms": 107.0}}
  ```

How it works:

- **Request IDs**: every response, errors included, carries an `X-Request-ID` header; quote it when reporting a
  problem. A client may send its own `X-Request-ID` to follow a request across services. It is reused only if it
  is up to 128 characters of letters, digits, `.`, `_` and `-`; anything else is replaced by a new ID, so nobody
  can inject fake lines into the logs. Lines written outside a request (startup) show `-`.
- The service logs from the worker thread that runs each endpoint. The ID still reaches those lines because it is
  kept in a context variable, which the thread receives a copy of; a thread-local variable would not.
- **One access line per request** (method, path, query, status, duration) replaces Uvicorn's own access log, and
  Uvicorn's other messages use the same format. Unexpected errors are logged with their traceback.
- **Timestamps are in UTC** (`Z`), unambiguous even when Madrid changes its clocks.
- The libraries that call AEMET only log warnings, and the **API key never appears in the logs**: it travels in
  a header, and a test checks the full debug output of a real-mode request for it.

The design, with the options considered, is in [ADR-0011](docs/adr/0011-logging.md).

## Limits and scaling

The service is built to run as **one Uvicorn process with a local SQLite file**, which is plenty for a team of
analysts: once the months of a range are cached, a request only reads the local database. Its limits are known:

| Limit | Why it is acceptable today |
|---|---|
| SQLite allows **one writer at a time** | Writes are rare (one per fetched month) and short; readers are never blocked thanks to WAL |
| The cache file is **local to one host** | One process on one host is the intended deployment |
| Coalescing and the circuit breaker **live in each process** | With N worker processes, the same month can be fetched up to N times and each process detects an AEMET outage by itself; results stay correct ([ADR-0009](docs/adr/0009-caching-strategy.md), [ADR-0010](docs/adr/0010-resilience.md)) |
| A **long range on an empty cache** is fetched month by month | Ten years of daily data means about 120 sequential fetches the first time; afterwards it is local |
| About **40 concurrent requests per process** (the thread pool) | Requests served from the cache are short ([ADR-0007](docs/adr/0007-concurrency-model.md)) |
| **No server-side pagination** | Each aggregation level has a maximum range, which keeps every response bounded |

How it would grow, step by step, each step only when the previous one is not enough:

1. **More worker processes on the same host** (`uvicorn --workers N`): safe today, since SQLite serializes writes
   and every write replaces a whole month.
2. **PostgreSQL instead of SQLite**, to share the cache between hosts. SQLAlchemy Core keeps most queries,
   Alembic replaces `PRAGMA user_version`, and PostgreSQL's advisory locks can coalesce fetches across processes.
3. **Shared coordination** (for example Redis) for the fetch locks and the circuit breaker state, so that all
   replicas fetch a month once and agree on whether AEMET is down.
4. **Background ingestion**: a scheduled job refreshes the current month every TTL and fills past months ahead of
   time, so no request ever waits for AEMET.
5. **Parallel fetches** of the months of one request, bounded by AEMET's rate limits, to shorten the first
   request for a long range.

## Front-end

The web interface in [`frontend/`](frontend/) is a single-page application in React and strict TypeScript, built
with Vite ([ADR-0012](docs/adr/0012-frontend-stack.md)). It shows the attribution AEMET requires on every page and,
in demo mode, a banner with the recorded period of each station, so the user knows which dates have data.

The browser only talks to the origin that served the page and calls the API through relative URLs (`/api/...`). In
development, the Vite dev server forwards them to the API on port 8000; in Docker, nginx does. The API therefore
needs no CORS configuration, and the page can read every response header, such as `X-Request-ID`.

To run it in development, start the API and the front-end in two terminals:

```bash
make demo            # terminal 1: API in demo mode on http://localhost:8000
make front-install   # once
make front-dev       # terminal 2: open http://localhost:5173
```

On Windows, run the front-end commands from PowerShell or Git Bash. In `cmd.exe`, a current directory written with
a lower-case drive letter (`c:\...`) makes Vitest load itself twice, and every test file fails with "Vitest failed
to find the current suite"; `cd /d C:\...` avoids it.

In Docker Compose, the `web` service builds the app in a Node image and serves the result with nginx on port 8080
([`frontend/Dockerfile`](frontend/Dockerfile), [`frontend/nginx.conf`](frontend/nginx.conf)). nginx runs as a
non-root user, like the API, and starts once the API reports healthy. Its configuration:

- forwards `/api/` to the `api` service, waiting up to five minutes for an answer: with an empty cache, a long range
  is fetched from AEMET month by month, and nginx's default of 60 seconds would cut it;
- caches the built scripts and styles for a year, since their names change with their content, and makes browsers
  revalidate `index.html` on every visit, so a new deployment is picked up at once;
- compresses scripts and styles (the API compresses its own JSON) and sends `X-Content-Type-Options` and
  `Referrer-Policy` headers. A Content Security Policy is left for later: the charts set inline styles, so it needs
  care.

Styles are CSS Modules, one per component, sharing the colours and spacing defined as CSS custom properties in
[`src/styles/global.css`](frontend/src/styles/global.css). The page has one colour scheme: white text on Sapphire
Blue (`#0042AC`), Ocean Cyan (`#00B3FB`) for interactive states such as focus, hover and the charts' cursor, and Neon
Jade (`#83FB80`) for a few highlights: the chart lines, the main button and checked boxes. Every text reaches a
contrast of 4.5:1 with its background and every line or border 3:1, the WCAG minimums; a lighter cyan is used for
links and a light red for errors, because the plain cyan and the usual red do not reach them on blue.

### The query form

The form asks for a station, a start and an end (included), an aggregation level and at least one measurement, and
sends the query when it is submitted ([ADR-0014](docs/adr/0014-query-form-validation.md)). Dates and times are typed
in Madrid time, the API's default, whatever the browser's time zone. The options, the official measurement labels and
the maximum range of each aggregation level come from `/api/v1/meta`.

It starts on a query that returns data: in demo mode, hourly means of the last two recorded days, which cover the
change to summer time on 30 March 2025; with real data, the last seven days.

A **Wind-energy metrics** option asks for the [wind-energy metrics](#wind-energy-metrics). It is disabled for
ten-minute records, which the API rejects with that parameter, and the table and the CSV show the metrics like any
other column, since both are built from the response's `fields`.

Before sending, the form checks that the end is later than the start and that the range is not too long for the
aggregation level, with one hour of margin: across a daylight saving time change the real duration, which the API
measures, differs from the calendar difference by up to an hour (see [Maximum range](#measurement-parameters)). The
form therefore never blocks a range the API accepts, and the API's answer settles the doubtful cases. When the API
rejects a parameter, such as a local time that does not exist, its message appears next to that field with the
request ID; any other error appears in an alert. While a query loads, the previous result stays on screen, dimmed,
instead of leaving a blank page. After a successful query, a summary shows the number of rows, how the dates were
interpreted, whether the data came from the cache, a warning when part of it is a stale copy, and the API's notice
when the range has no data.

### Charts

Below the summary, one chart per requested measurement shows it over time, all stacked on the same time axis, each
with its own scale ([ADR-0015](docs/adr/0015-charts.md)). With the wind-energy metrics, a chart of wind power
density follows; the other metrics stay in the table, so the page does not turn into a wall of charts. Moving the
cursor over one chart shows the reading at that moment on all of them: the value with its unit, the datetime with
its UTC offset and, for aggregated rows, samples and coverage.

The time axis is real time: each row sits at its instant, read from the API's datetime and its offset, not at its
position in the list. On the day summer time starts, the default demo query shows it: the 00:00 and 12:00 ticks are
eleven hours apart, one less than 12:00 and the next midnight, because Madrid's clocks skipped from 02:00 to 03:00.
Ticks fall on round Madrid hours, days, months or years, whatever the browser's time zone.

Gaps stay visible. Empty buckets arrive with null values and break the line; for ten-minute records, where a
missing record is simply absent, a break is added wherever more than ten minutes pass without one. A value with no
neighbours is drawn as a dot, since a line needs two points. When a result has more than 1,000 points per chart,
more than a chart is wide, a notice suggests the coarser aggregation that would show the trend more clearly, with
its approximate number of points.

The charts use Recharts, which with its dependencies weighs more than the rest of the front-end (about 107 kB against
85 kB gzipped), so they are loaded on demand: the page loads without them, and their code arrives with the first
result. If it cannot be loaded, a message replaces the charts and the summary and the table still work.

### The results table

Below the charts, a table shows the rows with the official labels of the response's `fields` block, in the API's
order, so a field added to the API appears without changing the front-end. The station column is left out: a query
covers one station, and the summary names it. Each datetime keeps its UTC offset (`2025-10-26 02:00 +01:00`),
because on the night summer time ends Madrid lives 02:00 to 03:00 twice and the offset tells the two rows apart. A
dash means no data.

Clicking a header sorts by that column, ascending first, then switching direction. Datetimes sort by instant, not as
text: `2025-10-26T02:00:00+01:00` sorts before `2025-10-26T02:00:00+02:00` as text, yet it happens an hour later.
Rows without a value go last in both directions. The rows are paginated in the browser, 50 per page: the maximum
range of each aggregation level keeps a response under about 9,000 rows (a year of hourly means), which the browser
sorts in an instant but would render slowly all at once (see [Limits and scaling](#limits-and-scaling)). A new
result starts on the first page, in the API's order.

When a range has no data at all, as with real data outside the stations' summer campaigns, the summary shows the
API's notice and the empty charts and table are left out; a button such as **Show the 169 empty hours** brings the
table back for whoever wants to see the empty buckets. A range with some data keeps every gap visible.

A `coverage` below 90 % is marked with ⚠, and in words for screen readers: the bucket has fewer observations than
a complete one, so its means are less representative (see [Data quality fields](#data-quality-fields)). The first
and last buckets show it when the range starts or ends partway through them; the default demo query, for example,
ends at midnight, and since the end is included, its last hour holds a single observation.

**Download CSV** is a plain link to the same query with `format=csv`. The file is the API's own export, with the
same labels and byte order mark, instead of a second CSV writer in TypeScript, and the cache serves it without
calling AEMET again. The link always matches the table on screen: it is hidden while the next query loads. If the
CSV request fails, Chrome cancels the download and the page stays as it was, without showing the API's message;
this is unlikely, since the same query has just succeeded and its months are cached.

### Talking to the API

The TypeScript types of every request and response are generated from the API's OpenAPI document
([ADR-0013](docs/adr/0013-frontend-api-client.md)). A script exports the document to
[`frontend/openapi.json`](frontend/openapi.json) without starting a server, and openapi-typescript turns it into
`frontend/src/api/schema.d.ts`. Both files are committed, so the front-end builds without Python. After changing the
API contract, run `make api-types` and commit both files: otherwise `make check` and CI fail, the backend job if the
API no longer matches `openapi.json`, the front-end job if the types no longer match it.

All requests go through a small client ([`src/api/client.ts`](frontend/src/api/client.ts)). An error answer becomes
an `ApiError` holding what the API said (code, message, offending parameter), the `X-Request-ID` and, for a 503,
`Retry-After`, so error messages can show the request ID to look for in the logs. TanStack Query caches the answers:
the options and the stations are fetched once, a network failure is retried once, and an error answer from the API
is not retried, because the API already retries AEMET and a 4xx does not change by repeating it.

## Limitations and next steps

### Known limitations

- **Maximum speed is not a gust**, and the temperature extremes are ten-minute means: AEMET's values within each ten
  minutes (`velx`, `tmn`, `tmx`) are not stored ([Wind-energy metrics](#wind-energy-metrics)).
- **The wind-energy metrics describe the site at sensor height** (about 10 m, below a turbine's hub), assume dry
  air, and give the power of the wind, not of a turbine ([Wind-energy metrics](#wind-energy-metrics)).
- **Station local time is a fixed UTC−03:00**; the clock actually used at the bases could not be verified
  ([Station local time](#station-local-time)).
- **The 48-hour grace** after which a month is final is an assumption until AEMET's publication delay is known
  ([Freshness](#freshness)).
- **Some AEMET details are unverified**: the exact answers for a rejected key (401) and for rate limiting (429), the
  real limits, and how long a data URL stays valid ([AEMET notes](docs/aemet-api.md#still-to-verify)).
- **The demo covers one month** (March 2025, both stations); other ranges return an empty result with a notice.
- **One process on one host**: fetch coordination and the circuit breaker live in each process
  ([Limits and scaling](#limits-and-scaling)).
- **The web app works in Madrid time only**; the API's `tz` parameter is not offered in the form
  ([The query form](#the-query-form)).
- **A failed CSV download shows no message**: the browser cancels it ([The results table](#the-results-table)).

### Next steps

- **More stations.** Another Antarctic station is one entry in the station registry
  ([`backend/app/domain/stations.py`](backend/app/domain/stations.py)); stations of another AEMET network, served by a
  different endpoint, need their own `WeatherSource` adapter. The cache, the aggregation, the API and the web app
  work per station identifier and need no change.
- Store AEMET's `velx`, `tmn` and `tmx` (a second schema version) for real gusts and temperature extremes.
- Server-side pagination, with a cursor by timestamp, if ranges longer than the per-level maximums are needed.
- A Content Security Policy in nginx that allows the charts' inline styles.
- A time zone selector in the form, for users outside Spain.
- Remembering the last query in the browser.
- Wind speed at hub height, extrapolated with a wind shear model and site parameters.
- The scaling path described in [Limits and scaling](#limits-and-scaling).

### Out of scope

Deliberately out of scope for this project, and natural next steps for a production service: authentication and
authorization, Kubernetes or cloud deployment, splitting into microservices, message queues (for example to
drive background ingestion), real PostgreSQL or Redis deployments, and internationalization of the interface.

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
| [0008](docs/adr/0008-cache-storage.md) | SQLite through SQLAlchemy Core for the cache: one file per mode, rebuilt instead of migrated, WAL and `BEGIN IMMEDIATE` writes for safe concurrency |
| [0009](docs/adr/0009-caching-strategy.md) | Cache-first by UTC month: final months are kept forever, months that can still change expire after a TTL, empty months are cached, concurrent fetches of a month are coalesced, and every response reports how it was served |
| [0010](docs/adr/0010-resilience.md) | When AEMET fails, expired months are served from their cached copy marked as stale, and a circuit breaker stops calling AEMET for a cool-down so no request waits for retries in vain |
| [0011](docs/adr/0011-logging.md) | Standard logging with a small JSON formatter, a request ID carried in a context variable and echoed as `X-Request-ID`, one access line per request, UTC timestamps |
| [0012](docs/adr/0012-frontend-stack.md) | React + Vite front-end in strict TypeScript 5.9 (not 7, which the type-aware tooling does not support yet), ESLint + Prettier + Vitest, same-origin calls through a proxy instead of CORS, CSS Modules |
| [0013](docs/adr/0013-frontend-api-client.md) | Front-end types generated from a committed OpenAPI document with drift checks in CI, a small `fetch` client whose errors keep the request ID, TanStack Query retrying network failures only |
| [0014](docs/adr/0014-query-form-validation.md) | The query form checks ranges on calendar values with one hour of margin and leaves daylight saving time cases to the API, validates on submit, shows API parameter errors next to their field, and starts on a query with data |
| [0015](docs/adr/0015-charts.md) | Recharts small multiples on a shared time axis by instant, ticks on Madrid's calendar, visible gaps in ten-minute data, and a suggested coarser aggregation above 1,000 points |
| [0016](docs/adr/0016-wind-energy-metrics.md) | Optional wind-energy metrics per bucket (cubic mean and maximum speed, temperature extremes, air density, wind power density), computed per observation before averaging, from the stored ten-minute means |

## Development

### Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/), or only [Docker](https://docs.docker.com/get-docker/)
  to run the stack.
- [Node.js](https://nodejs.org/) 26 (LTS) and npm for the front-end; the version is pinned in
  [`frontend/.nvmrc`](frontend/.nvmrc).
- GNU Make (optional). Every target is a shortcut for the plain command listed below.
  On Windows it can be installed with `winget install ezwinports.make`.

### Configuration

The backend reads its configuration from environment variables or from a `backend/.env` file, which is
git-ignored. To start, copy [`backend/.env.example`](backend/.env.example) to `backend/.env`.

| Variable | Default | Description |
|---|---|---|
| `DEMO_MODE` | `false` | Serve recorded AEMET responses instead of calling the real API. No API key is needed. |
| `DEMO_DATA_DIR` | `sample_data/demo` | Folder with the recorded responses used in demo mode, relative to `backend/` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `LOG_FORMAT` | `text` (`json` in Docker Compose) | `text` for a terminal, `json` for one JSON object per line |
| `CACHE_DB_PATH` | `data/cache.sqlite3`, or `data/cache-demo.sqlite3` in demo mode | SQLite file of the cache, relative to `backend/` |
| `CACHE_TTL_MINUTES` | `60` | How long a month that can still change is served from the cache before it is fetched again |
| `CACHE_GRACE_HOURS` | `48` | Hours after a month ends during which AEMET may still add data; a month fetched later is final |
| `UPSTREAM_COOLDOWN_SECONDS` | `60` | After a failed fetch, seconds during which AEMET is not called and cached copies are served |
| `AEMET_API_KEY` | none | Personal AEMET OpenData API key. Required when `DEMO_MODE` is `false`. |
| `AEMET_BASE_URL` | `https://opendata.aemet.es/opendata` | AEMET OpenData base URL |
| `AEMET_TIMEOUT_SECONDS` | `30` | Timeout of each HTTP request to AEMET |
| `AEMET_MAX_ATTEMPTS` | `3` | Attempts per monthly window when AEMET fails transiently |
| `MAX_RANGE_DAYS_NONE` | `31` | Longest range accepted without aggregation, in days of real elapsed time (about 4,500 ten-minute records). See [Maximum range](#measurement-parameters) |
| `MAX_RANGE_DAYS_HOURLY` | `366` | Longest range accepted with hourly aggregation, in days of real elapsed time |
| `MAX_RANGE_DAYS_DAILY` | `3660` | Longest range accepted with daily aggregation, in days of real elapsed time (ten years) |
| `MAX_RANGE_DAYS_MONTHLY` | none | Longest range accepted with monthly aggregation (unlimited by default) |

`DEMO_MODE` defaults to `false` on purpose: a deployment that forgets its API key refuses to start with a clear
message, instead of silently serving demo data. The API key is held as a secret value that is never printed or
logged.

The range limits keep every response bounded in size. A longer request is rejected with HTTP 422 and a message
suggesting a shorter range or a coarser aggregation, instead of being paginated.

### Tests and coverage

Tests never call the real AEMET API: upstream answers are mocked or replayed from recorded responses. CI measures
coverage while it runs them. The backend covers 98 % of its lines and branches, and CI fails below 95 %
(`fail_under` in [`backend/pyproject.toml`](backend/pyproject.toml)), a margin that lets small refactors through
while catching code added without tests. The front-end reports its coverage (99 % of lines, 93 % of branches)
without a threshold. Both HTML reports can be downloaded from every CI run, as the `backend-coverage` and
`frontend-coverage` artifacts. A percentage only says which lines ran, not whether a test would notice them break,
so it complements the tests' assertions rather than replacing them.

### Commands

Run them from the repository root.

| Make target | Equivalent command | Purpose |
|---|---|---|
| `make install` | `uv sync --locked --directory backend` | Install backend dependencies exactly as pinned in `uv.lock` |
| `make run` | `uv run --directory backend uvicorn app.main:create_app --factory --reload` | Start the API with auto-reload on <http://localhost:8000> (interactive docs at `/docs`) |
| `make demo` | Bash: `DEMO_MODE=true uv run --directory backend uvicorn app.main:create_app --factory --reload`<br>PowerShell: `$env:DEMO_MODE="true"; uv run --directory backend uvicorn app.main:create_app --factory --reload` | Same as `run`, in demo mode (recorded data, no API key needed) |
| `make test` | `uv run --directory backend pytest` | Run the backend test suite |
| `make coverage` | `uv run --directory backend pytest --cov --cov-report=term-missing --cov-report=html` | Run the backend tests measuring line and branch coverage; fails below 95 %. HTML report in `backend/htmlcov`. CI runs this instead of `make test` |
| `make lint` | `uv run --directory backend ruff check .`<br>`uv run --directory backend ruff format --check .` | Check backend linting and formatting without changing files |
| `make format` | `uv run --directory backend ruff check --fix --exit-zero .`<br>`uv run --directory backend ruff format .` | Apply safe lint fixes, then format the backend code (remaining lint issues are reported by `make lint`) |
| `make typecheck` | `uv run --directory backend mypy` | Backend static type checking in strict mode |
| `make openapi-check` | `uv run --directory backend python -m scripts.export_openapi --check` | Fail if `frontend/openapi.json` no longer matches the API |
| `make api-types` | `uv run --directory backend python -m scripts.export_openapi`<br>`npm --prefix frontend run generate:api` | Regenerate `frontend/openapi.json` and the front-end API types after changing the API contract |
| `make front-install` | `npm --prefix frontend ci` | Install front-end dependencies exactly as pinned in `package-lock.json` |
| `make front-dev` | `npm --prefix frontend run dev` | Start the front-end dev server on <http://localhost:5173>, forwarding `/api` to port 8000 |
| `make front-test` | `npm --prefix frontend test` | Run the front-end test suite (Vitest) |
| `make front-coverage` | `npm --prefix frontend run coverage` | Run the front-end tests with a coverage report, without a threshold. HTML report in `frontend/coverage`. CI runs this instead of `make front-test` |
| `make front-lint` | `npm --prefix frontend run lint` | Check front-end linting (ESLint) and formatting (Prettier) without changing files |
| `make front-format` | `npm --prefix frontend run format` | Apply lint fixes, then format the front-end code |
| `make front-typecheck` | `npm --prefix frontend run typecheck` | Front-end static type checking (`tsc -b`) |
| `make front-types-check` | `npm --prefix frontend run check:api` | Fail if the front-end API types no longer match `frontend/openapi.json` |
| `make front-build` | `npm --prefix frontend run build` | Type-check and build the front-end for production into `frontend/dist` |
| `make front-check` | The `front-lint`, `front-typecheck`, `front-types-check`, `front-test` and `front-build` commands above | Every front-end check |
| `make check` | The `lint`, `typecheck`, `openapi-check` and `test` commands, then `make front-check` | The checks CI runs, backend and front-end (CI also measures coverage) |
| `make up` | `docker compose up --build` | Build and start the Docker stack: web app on port 8080, API on port 8000 (demo mode by default) |
| `make down` | `docker compose down` | Stop the Docker stack. The cache volume is kept; `docker compose down -v` deletes it |

## Project status

| Part | Scope | Status |
|---|---|---|
| Part 1 | API with time zone and DST handling, aggregation, data quality fields, CSV export, demo mode, Docker | Done |
| Part 2 | SQLite cache of AEMET data, resilience when AEMET fails, structured logging | Done |
| Part 3 | TypeScript front-end with table and charts | Done |
| Extras | Wind-energy metrics (cubic mean speed, maximum speed, air density, wind power density), CI polish | Done |
