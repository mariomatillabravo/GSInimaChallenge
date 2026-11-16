# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Web API (Python + FastAPI) that retrieves Antarctic weather data from the AEMET OpenData API, with an SQLite cache and a TypeScript front-end.

## Language

- Communicate with the developer in **Spanish**.
- Everything in the repository is in **English**: code, comments, docstrings, README, ADRs and commit messages.

## Working agreement

- Do not implement anything until the developer has approved the plan for that step.
- For every non-trivial decision, explain the alternatives considered and their trade-offs, so the developer can defend and modify it without assistance.
- For subtle topics (time zones, DST, caching, concurrency), stop and check understanding before moving on.
- Ask questions in small batches, one topic at a time, and never skip a point.
- Mark anything uncertain as **"to verify"** instead of assuming it, especially AEMET API details (endpoints, parameters, formats, limits, station identifiers).
- Never hardcode secrets. Configuration comes from environment variables; `.env` is git-ignored and `.env.example` documents every variable.

## Delivery order

The goal is to deliver everything. Work block by block: each block is finished, tested and documented before the next one starts. Never leave several blocks half-done in parallel.

1. **Part 1**: core API, DST test suite, demo mode, README.
2. **Part 2**: SQLite cache, resilience, logging.
3. **Part 3**: TypeScript front-end.
4. **Extras**: wind-energy metrics, CSV export, CI polish, other nice-to-haves.

Flag early if the plan does not fit the deadline. Anything left unfinished is listed as a TODO in the README, never delivered half-broken.

Each completed block gets an annotated tag: `v0.1.0` (Part 1), `v0.2.0` (Part 2), `v0.3.0` (Part 3), `v1.0.0` (final delivery).

## Documentation

- The README is living documentation: update it in the same step a decision is implemented, inside the relevant section. Explain what was decided and why (context, alternatives, reasoning, consequences).
- Never write the README as a changelog and never reference commits ("Commit 1: ...", "In this commit ..."). When a decision changes, rewrite the text so it reflects the current state.
- Keep the README consistent with the ADRs in `docs/adr/`: the README gives the short explanation and links to the ADR for the full reasoning. Superseded decisions are recorded in the ADRs.
- Remind the developer to update `docs/AI_USAGE.md` at each milestone.

## Commits

- Small, meaningful commits following [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `ci:`, `build:`).
- Propose the commit message at each step, then ask the developer for permission to commit and push. Create the commit and push it only after explicit approval.

## Settled decisions

- **Stack**: Python 3.12 + FastAPI (backend, managed with uv); React + Vite + TypeScript (frontend, npm); Docker Compose.
- **Concurrency model**: synchronous stack (`def` endpoints, sync `httpx.Client`, sync SQLAlchemy Core). Never call blocking code from an `async def` endpoint.
- **Input time zone**: datetimes without an explicit time zone or offset are interpreted as `Europe/Madrid`. Every response states how the input was interpreted.
- **DST input policy**: non-existent and ambiguous local times are rejected with HTTP 422; an explicit offset always disambiguates.
- **Output time zone**: datetimes are returned in `Europe/Madrid` and always include the UTC offset (e.g. `+02:00`).
- **Internal time handling**: always UTC with timezone-aware datetimes. Naive datetimes are never used.
- **Aggregation**: daily and monthly buckets follow the station's local time; bucket labels are expressed in `Europe/Madrid`.
- **Data quality**: aggregated rows include `samples`, `expected_samples` and `coverage` (computed at query time, not stored).
- **Output fields**: JSON uses snake_case keys plus a `fields` block with the official labels; CSV export and UI use the official labels.
- **Caching**: SQLite through SQLAlchemy Core, filled by fixed monthly UTC chunks; schema versioned with `PRAGMA user_version` (no Alembic).
- **Cache storage**: one default file per mode plus a data-source guard; a version or data-source mismatch rebuilds the cache instead of migrating it; WAL, and every write goes through `write_transaction()` (`BEGIN IMMEDIATE`); a re-fetched month is replaced whole (ADR-0008).
- **Freshness**: cache-first with a single read path; a month fetched at least `CACHE_GRACE_HOURS` (48) after it ended is final, otherwise it expires after `CACHE_TTL_MINUTES` (60); empty months are cached; the month in progress is fetched up to now and future months are skipped; the fetch time is the start of the request, from an injected clock (ADR-0009).
- **Concurrent fetches**: single flight per station and month within a process; requests that wait for a shared fetch share its outcome and report the month as fetched (ADR-0009).
- **Resilience**: when a fetch fails for any upstream error, an expired month with a cached copy is served as stale; a circuit breaker then skips AEMET for `UPSTREAM_COOLDOWN_SECONDS` (60), and months without a copy fail fast with 503 and `Retry-After` (ADR-0010).
- **Cache metadata**: `source` stays `aemet`/`demo`; `metadata.cache` holds `status` (`hit`/`miss`/`partial`), `last_updated` (oldest fetch among months that can still change) and `stale`, repeated in the `X-Cache-Status` and `X-Data-Stale` headers on JSON and CSV.
- **Logging**: standard `logging` with text or JSON lines (`LOG_FORMAT`), UTC timestamps; a request ID in a `ContextVar`, echoed as `X-Request-ID` (safe client IDs reused), on every log line and every response, 500s included; one access line per request; the API key is never logged (ADR-0011).
- **Demo mode**: the whole application runs without an AEMET API key, serving recorded AEMET responses through the same data-source interface as the real client.
- **Front-end tooling**: TypeScript 5.9 (7 lacks the JS API that typescript-eslint and openapi-typescript need), ESLint strictTypeChecked + Prettier, Vitest + Testing Library + jsdom, Node 26 pinned in `frontend/.nvmrc` (ADR-0012).
- **Same origin**: the browser calls relative `/api/...` URLs, proxied by Vite in development and by nginx in Docker (web on :8080, API on :8000); no CORS (ADR-0012).
- **API types**: generated from the committed `frontend/openapi.json` (`make api-types`); `openapi-check` and `front-types-check` fail on drift. TanStack Query retries network failures once and API errors never; errors keep the request ID (ADR-0013).
- **Form**: inputs are Madrid wall-clock times, never turned into a browser-zone `Date`; ranges are checked on calendar values with one hour of margin, and the API's 422 settles DST cases (ADR-0014).
- **Results**: table columns come from the response's `fields`, datetimes show their offset and sort by instant, coverage below 90 % is flagged in words, CSV is the API's own export; charts are Recharts small multiples on a time axis by instant with visible gaps, loaded on demand (ADR-0015).
- **Wind-energy metrics**: optional `metrics=extended` on aggregated levels, each metric only when its input types are requested; air density and power density are computed per observation before averaging; maximum speed and temperature extremes come from the ten-minute means, not gusts (ADR-0016).
- **Discarded records**: the parser only counts them; each adapter logs the count per fetched month at INFO, when there are any.
- **Coverage**: CI measures backend line and branch coverage with `make coverage` and fails below 95 %; front-end coverage is reported without a threshold.
- **Commands**: a Makefile provides shortcuts; the README lists the full equivalent command for every target.

## Out of scope

Do not implement. Mention only in the README as future evolution:
authentication/authorization, Kubernetes or cloud deployment, microservices, message queues, real PostgreSQL/Redis deployments, internationalization (i18n).

## Code quality

- Type hints everywhere.
- Transformation logic (parsing, time zone conversion, aggregation) lives in pure functions.
- Tests never call the real AEMET API: upstream calls are mocked or replayed from recorded fixtures.
