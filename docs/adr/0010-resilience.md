# ADR-0010: Serving stale data and a circuit breaker when AEMET fails

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

With the cache of [ADR-0009](0009-caching-strategy.md), a request only needs AEMET for months that are missing
or expired. Before this decision, a failed fetch always turned into an error, even when an older copy of the
month was sitting in the cache. Two more facts matter:

- A failed fetch is slow. The client retries transient failures with backoff
  ([ADR-0004](0004-aemet-client.md)), so with 3 attempts and a 30-second timeout a single fetch can take more than
  a minute and a half before giving up. Coalescing ([ADR-0009](0009-caching-strategy.md)) makes concurrent
  requests share that wait, but the next request after a failure would pay it again.
- Data a few hours old is far more useful to an analyst than an error, as long as the response says so.

## Options considered

**What a failed fetch returns**

1. **The cached copy, marked as stale**, when the month has one; an error when it has none. A range is never
   served incomplete without saying so.
2. **Always an error**: honest but unhelpful, and it throws away data the service already holds.

**Which failures allow serving the copy**

1. **Any upstream error**: unreachable or rate limited (503), timeout (504), and 5xx, unreadable answers or a
   rejected API key (502). The client keeps getting data, flagged as stale; the operator sees the failure in the
   logs.
2. **Only transient failures** (503, 504): a rejected key would surface to clients as an error, making a
   configuration mistake more visible at the cost of leaving clients without data.

**Avoiding a round of retries on every request while AEMET is down**

1. **Circuit breaker**: after a failed fetch, AEMET is not called for a cool-down period. Meanwhile cached copies
   are served at once and months without a copy fail at once; after the cool-down the next fetch tries again.
   Bounded latency during an outage, no hammering of a struggling service, and a well-known pattern.
2. **Fewer retries when a copy exists**: a single short attempt. It needs the retry policy passed through the
   `WeatherSource` interface, and every request still pays one timeout while AEMET is down.
3. **Stale-while-revalidate**: always serve an expired copy at once and refresh it in a background thread. No
   waiting at all, but it brings background threads and their errors into a synchronous service, and data stays
   one TTL behind even when AEMET is healthy.

## Decision

- **Option 1 for each question.** When a fetch fails, an expired month with a cached copy is served from it, any
  upstream error qualifies, and a circuit breaker stops calling AEMET for `UPSTREAM_COOLDOWN_SECONDS` (60).
- **Reporting**: `metadata.cache.stale` is `true` when at least one month was served this way, and
  `last_updated` (the oldest fetch time among months that can still change) then tells how old the copy is. The
  `X-Data-Stale` header always carries `true` or `false`, on JSON and CSV responses. A stale month was not
  fetched, so it counts like a cache hit in `status`.
- **Circuit breaker** (`app/services/circuit.py`): one per process, shared by both stations, since an AEMET
  outage affects them alike, and driven by the same injected clock as the service. One failed fetch opens it,
  because that fetch has already been retried. While it is open, a month without a copy fails with
  `UpstreamCoolingDownError`: a 503 with a `Retry-After` header, in whole seconds rounded up. Once the cool-down
  ends, fetches are allowed again; a success closes the circuit, and another failure opens it for a new period.
- **Logs**: a warning for every month served stale and when the circuit opens, and an info message when AEMET
  answers again.

## Consequences

- During an outage, requests for cached data answer at once with a clear stale flag. Only months that were never
  fetched fail, and they fail fast with a hint of when to retry.
- AEMET receives at most one fetch per cool-down period from each process while it is failing, plus the shared
  fetch that opened the circuit.
- A rejected API key also leads to stale data rather than errors for cached months; it shows up as warnings in
  the logs, and months without a copy still return 502.
- If AEMET recovers during a cool-down, missing months keep failing until it ends: at most
  `UPSTREAM_COOLDOWN_SECONDS`.
- The breaker lives in each process: with N worker processes, each one discovers the outage by itself.
- Tests drive time with a fake clock. They cover the circuit's boundaries and the service end to end: serving a
  stale copy, skipping AEMET while cooling down, recovering afterwards, final months being unaffected, and
  concurrent requests all getting the copy after one shared failure. Removing the stale fallback, the breaker or
  its check makes them fail.
