# ADR-0004: AEMET client, data cleaning and upstream errors

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

The AEMET Antarctica endpoint has several particularities, verified against the real API
(see [docs/aemet-api.md](../aemet-api.md)):

- A two-step protocol: an envelope first, then a URL with the data.
- Errors are reported in the envelope's `estado` field while the HTTP status stays 200.
- At most one month per request.
- Missing values are the string `"NaN"`, records may come unsorted, and each record carries a quality flag
  (`qdato`: 1 bad, 0 good).

The rest of the application (aggregation, cache, API) should not know any of this, and tests must never call the
real API. Demo mode must work without an API key.

## Options considered

**Shape of the integration**

1. **A `WeatherSource` port** (a `typing.Protocol` with `fetch(station, start, end)`) implemented by an AEMET
   client and by a recorded source; parsing in pure functions.
2. **Calling AEMET directly from the service layer**: fewer types, but the upstream quirks leak everywhere and
   demo mode would need a separate code path.

**HTTP and retry libraries**

1. **`httpx` (sync) + `tenacity`, mocked in tests with `respx`**: mature, widely known, and `respx` blocks any
   unmocked request. Starlette's `TestClient` prefers `httpx2`, so `httpx2` is a development-only dependency used
   by that test client; application code stays on `httpx`.
2. **`requests`**: very common, but no async path if ever needed and less convenient to mock at transport level.
3. **Move everything to `httpx2`**: a single library, but young (first release in 2026) and not supported by
   `respx`.

## Decision

- **Port and adapters.** `WeatherSource` returns cleaned, sorted observations in UTC for an inclusive range; an
  empty list means "no data", not an error. `AemetAntarcticaClient` and `RecordedWeatherSource` implement it, and
  both use the same pure parser, so demo mode exercises the real parsing code.
- **Monthly windows.** A range is split into calendar months in UTC, which is both AEMET's limit and the unit
  that the cache will store. Each window ends one second before the next month starts, so no record is fetched
  twice.
- **Cleaning rule**, applied when parsing:
  - `"NaN"`, `null`, a non-numeric value or an absent field is a missing value;
  - a record with `qdato = 1` has all its values treated as missing;
  - a record left without any value, or without a valid UTC timestamp, is discarded;
  - records are sorted by time, and a repeated timestamp keeps the last record.
- **Retries** with exponential backoff (up to `AEMET_MAX_ATTEMPTS` per window) for network errors, timeouts,
  HTTP 429 or `estado: 429`, and HTTP 5xx. A rejected API key (401/403) and other permanent errors are not
  retried.
- **Error classification**, reported by the API as:

  | Persistent failure | Error | HTTP status |
  |---|---|---|
  | AEMET unreachable or rate limiting | `UpstreamUnavailableError` | 503 |
  | AEMET too slow | `UpstreamTimeoutError` | 504 |
  | 5xx, rejected key, unexpected `estado` or malformed response | `UpstreamError` | 502 |

- The API key is sent only in the `api_key` header of the first request and never appears in error messages.

## Consequences

- Upstream quirks live in two modules (`aemet_parser.py`, `aemet.py`); swapping the data source is a new adapter.
- Contract tests run the parser against real recorded responses, and the client is tested with `respx`; a
  request without a mocked route fails the test, so the real AEMET is never called.
- A second AEMET network with another endpoint would need its own adapter; adding another Antarctic station is
  only a registry entry.
- If `respx` gains `httpx2` support, migrating the client is limited to `aemet.py`.
