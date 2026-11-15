# ADR-0009: Caching strategy

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

The cache storage is described in [ADR-0008](0008-cache-storage.md). This ADR decides what is fetched, when a
cached copy may be served, and how a response tells the client where its data came from. Facts that shape it:

- AEMET serves at most one calendar month per request, rate limits its clients, and answers in two steps.
- Antarctic data only grows at the end: past observations rarely change, but late records can be published after
  the fact, and a month in progress gains data every ten minutes.
- How long AEMET takes to publish late Antarctic observations is unknown (to verify), and cannot be checked now:
  the 2026 campaign data ends on 13 March.
- Many months have no data at all (the stations mostly report during austral summer campaigns).

## Options considered

**Unit of caching**

1. **Fixed calendar months in UTC**: the same unit AEMET accepts per request, so one missing month is one upstream
   request. A request for part of a month fetches the whole month once, and later requests anywhere in that month
   are served from the cache.
2. **The exact ranges requested**: no extra data on the first request, but overlapping ranges need interval
   bookkeeping, and every new range calls AEMET again.

**When a cached month is fetched again**

1. **Final months forever, the others after a TTL**: a month fetched at least a grace period (48 h) after it
   ended is final. A month in progress, or one that ended recently, is served for a TTL (1 h) and then fetched
   again.
2. **A single TTL for everything**: simple, but it keeps fetching years of data that will never change.
3. **Never refetch**: the month in progress would freeze at its first fetch.

**Fetch time recorded for a month**

1. **The moment the request started**: conservative. The data is at least as recent as that instant, and every
   month of a request is judged against the same "now".
2. **The moment the fetch finished**: overstates freshness. Anything AEMET published during a slow fetch would
   count as included, and a month could become final a few seconds too early.

**Months in progress and in the future**

1. **Fetch the month in progress up to now, skip future months**: no request can depend on how AEMET answers an
   end date in the future (to verify), and no empty future month is ever stored.
2. **Always fetch whole months**: simpler, but it relies on that unverified behaviour and stores future months as
   empty.

**How a response reports the cache**

1. **Keep `source` (`aemet`/`demo`) and add a `cache` block** with `status` (`hit`, `miss`, `partial`) and
   `last_updated`, repeated as the `X-Cache-Status` header. Origin and freshness are separate facts, and a range
   that mixes cached and fetched months is described honestly.
2. **Widen `source`** (`aemet`, `demo`, `cache`): cannot express "demo data from the cache" or a mixed range.
3. **Per-month details**: the most transparent, but it turns an internal detail (the size of the chunks) into a
   public contract.
4. **Headers only**: invisible in the JSON body, where every other piece of metadata is, and the standard header
   for stale data (`Warning: 110`) is obsolete since RFC 9111.

## Decision

- **Cache-first by UTC month** (option 1). For each request the service splits the range into months, fetches
  those that are missing or expired, stores them (replacing older copies), then reads the whole range from the
  cache and aggregates it. Reading always from the cache, even right after a fetch, gives a single read path.
- **Freshness** (option 1), as pure functions in `app/domain/freshness.py`:
  - final when `fetched_at ≥ end of month + grace`;
  - otherwise expired when `now − fetched_at ≥ TTL`;
  - TTL and grace are configurable (`CACHE_TTL_MINUTES=60`, `CACHE_GRACE_HOURS=48`). The grace is an assumption
    until AEMET's publication delay is verified.
- **Empty months are cached** (`row_count = 0`) under the same rules, so a final empty month is never requested
  again.
- **Fetch time = start of the request** (option 1), truncated to whole seconds. The clock is injected, so tests
  move time forward.
- **Month in progress fetched up to now; future months skipped** (option 1).
- **Reporting** (option 1): `metadata.cache.status` is `hit` when nothing had to be fetched (also for a range
  entirely in the future), `miss` when every month was fetched and `partial` otherwise. `last_updated` is the
  oldest fetch time among the months of the range that can still change, written in Europe/Madrid, or `null` when
  all are final. `X-Cache-Status` repeats the status, so CSV downloads, which have no metadata, carry it too.

## Consequences

- Repeated and overlapping queries no longer reach AEMET, and finished campaigns are fetched only once.
- The first request for a long range with an empty cache still fetches every month, one after another: a ten-year
  daily series means 120 upstream requests. Later requests for any part of it are local.
- A failed fetch reaches the client as an error, even if an older copy of the month is cached, and nothing is
  stored. Concurrent requests for the same missing month may each fetch it; replacing whole months keeps the
  stored result correct.
- A wrong grace only delays or anticipates when a month becomes final: too short and a late record may be missed
  until the cache is rebuilt; too long and a recent month is fetched a few extra times.
- Tests cover the rules as pure functions (with exact boundaries) and the service end to end with a counting fake
  source, a controllable clock and the real SQLite repository; deliberately breaking the fetch time, the
  clamping of the current month, the skipping of future months or the TTL boundary makes them fail.
