# ADR-0008: Cache storage in SQLite through SQLAlchemy Core

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

AEMET serves at most one month per request, rate limits its clients and answers slowly, so the service keeps the
data it has already fetched in a local SQLite cache. Constraints:

- The cache is **regenerable**: everything in it can be fetched again from its data source. Losing it costs time
  and upstream quota, never information.
- Requests are served from a **thread pool** ([ADR-0007](0007-concurrency-model.md)), and the service may run as
  **several worker processes** sharing one file (`uvicorn --workers N`).
- **Demo mode** goes through the same cache as real data, but its recorded months must never be served as real
  AEMET data: most months are "no data" in the demo.

This ADR covers how the data is stored. The caching strategy (which months are fetched and when they are
refreshed) is recorded in [ADR-0009](0009-caching-strategy.md).

## Options considered

**Data access library**

1. **SQLAlchemy Core**: table definitions in Python, a SQL expression builder, a connection pool and SQLite's
   `INSERT ... ON CONFLICT` upsert. Close to SQL, so every query stays readable.
2. **SQLAlchemy ORM**: sessions, identity map and mapped classes. Built for object graphs, not for bulk time series
   that end up in pandas; extra overhead and concepts for no gain here.
3. **Plain `sqlite3`**: no dependency, but connection pooling, thread handling and SQL strings would be written by
   hand, and moving to another database would mean rewriting every query.

**Schema changes**

1. **`PRAGMA user_version` and rebuild on mismatch**: SQLite keeps a free integer in the file header. When it
   differs from the code's schema version, in either direction (an older file, or a newer one after a downgrade),
   the cache tables are dropped and created again.
2. **Refuse to start** and ask the operator to delete the file: never deletes anything without permission, but
   adds manual work for a file with no value of its own.
3. **Migrations** (Alembic or hand-written steps): keep the data, at the cost of maintaining a migration history
   for data that can be fetched again.

**Storing a month that is fetched again**

1. **Replace the whole month**: delete the month's rows, insert the new ones and upsert its `fetched_chunks` row,
   in one transaction. The month is always an exact copy of the latest fetch.
2. **Upsert row by row** (`INSERT ... ON CONFLICT DO UPDATE`): fewer writes, but a record the source stops
   publishing (for example one later flagged as bad quality, which the parser discards) would stay in the cache
   forever, and `row_count` would no longer match the rows stored.

**What reads return**

1. **`Observation` objects**: the type every `WeatherSource` already returns, so aggregation and the service do
   not change, and the cache is invisible to the rest of the code.
2. **A pandas DataFrame** (`pd.read_sql`): faster for very long ranges (ten years are about 525,000 rows) because
   no object is built per row, but it breaks the type boundary and changes the aggregation input.

**Keeping demo and real data apart**

1. **One default file per mode plus a guard**: `data/cache.sqlite3` for real data and `data/cache-demo.sqlite3`
   for the demo, so switching modes keeps both caches. The file also records its data source in a one-row table,
   `cache_info`, and is rebuilt like a version mismatch if it does not match the running mode (for example when
   `CACHE_DB_PATH` points both modes to the same file).
2. **Only the guard**: one file, rebuilt at every mode switch, which throws away the real cache.
3. **Only separate files**: simplest, but one manual setting reintroduces the problem silently.
4. **A `source` column in every primary key**: both datasets in one file; every query must filter by source.

**Transaction control**

Two problems were found with concurrent tests (8 engines, playing worker processes, opening one new file at the
same instant, 20 rounds):

- In the driver's default mode (Python 3.12 "legacy transaction control"), `CREATE`/`DROP TABLE` and
  `PRAGMA user_version` take effect immediately and survive a rollback, so a rebuild interrupted halfway would
  leave a broken schema.
- A transaction opened with a plain `BEGIN` that reads and then writes fails at once with "database is locked"
  when another connection writes in between: 112 of 160 schema checks failed. Waiting cannot help, because what
  the transaction read is already outdated, so `busy_timeout` does not apply. Opening it with `BEGIN IMMEDIATE`,
  which takes the write lock before the first read, made the other connections wait their turn: 0 failures.

The options:

1. **SQLAlchemy emits `BEGIN`, or `BEGIN IMMEDIATE` for writes**: the documented SQLAlchemy recipe. The driver is
   told never to open transactions itself (`isolation_level = None`) and an event emits the `BEGIN`. Solves both
   problems.
2. **Driver defaults**: solves neither.
3. **`autocommit=False`** (the PEP 249 mode, default from Python 3.16): schema changes become transactional, but
   the driver always opens a plain `BEGIN` itself, so `BEGIN IMMEDIATE` is impossible and the second problem
   remains.

## Decision

- **SQLAlchemy Core 2.1**, behind a small `app/db` package. The engine is created once at startup and disposed of
  at shutdown.
- **Tables** (schema version 1):

  | Table | Columns | Primary key |
  |---|---|---|
  | `measurements` | `station_id`, `ts_utc` (Unix epoch seconds), `temperature`, `pressure`, `speed` (missing = NULL) | `station_id`, `ts_utc` |
  | `fetched_chunks` | `station_id`, `chunk_start` (`YYYY-MM`, UTC), `fetched_at` (epoch seconds), `row_count` | `station_id`, `chunk_start` |
  | `cache_info` | `data_source` (`aemet` or `demo`), a single row | `id` (always 1) |

  Timestamps are integers in UTC: compact, ordered as numbers, and free of time zone parsing. SQLAlchemy's
  `DateTime` type would store naive text in SQLite, which the project never uses. `station_id` is the station's
  identifier in the registry (`juan-carlos-i`). Both data tables are `WITHOUT ROWID` tables: rows are stored in
  primary key order, which is the range scan the cache performs, with no separate index.
- **Repository** (`CacheRepository`): it reports which months are cached, stores a whole month and reads a time
  range back. A re-fetched month is **replaced** (option 1), and reads return **`Observation` objects**
  (option 1). It holds no freshness rules: deciding when to fetch belongs to the service.
- **Schema changes**: option 1, `PRAGMA user_version` and a rebuild on any mismatch, logged as a warning.
- **Demo and real data**: option 1, one default file per mode plus the `cache_info` guard.
- **Per-connection settings**: `busy_timeout = 5000` (wait up to 5 s for another connection's write lock instead
  of failing) and `synchronous = NORMAL` (with WAL, a power cut may lose the last transactions but never corrupts
  the file: acceptable for a cache).
- **WAL journal mode**, enabled once at startup: readers and the single writer work at the same time. The mode is
  stored in the file, so it is not repeated per connection. It cannot be changed inside a transaction, and
  switching a new file can fail at once when several processes try together (23 of 160 attempts), so the switch
  is retried up to 10 times with short random pauses (tenacity, already a dependency).
- **Transaction control**: option 1. Every unit of work that writes uses `write_transaction()`
  (`BEGIN IMMEDIATE`); reads use a plain `BEGIN`.
- **Threads**: for a file database SQLAlchemy uses a `QueuePool` and disables `sqlite3`'s `check_same_thread`
  guard. The guard forbids using a connection from a thread other than the one that created it; the pool lends
  each connection to one thread at a time, so a connection may move between threads but is never used by two at
  once. The project rule follows: each unit of work opens its own connection, and a `Connection` object is never
  shared between threads.

## Consequences

- A rebuild is atomic: if it fails halfway, the previous schema and data remain. Concurrent startups take turns:
  the first creates the schema, the others find it current.
- Concurrency tests run on real temporary files (WAL does not exist for `:memory:` databases, and SQLAlchemy gives
  each thread its own `:memory:` database). They were checked against the rejected designs: removing
  `BEGIN IMMEDIATE`, the transaction control event or the WAL retry makes them fail.
- Writes are serialized by SQLite itself, across threads and processes, so several workers can share the file
  safely. Readers see a month either before or after a replacement, never halfway, which a test checks while
  writers keep replacing the same month.
- Reading a very long range builds one object per row. If that ever shows up in profiles, a DataFrame read path
  for aggregation is the contained optimisation.
- The pool keeps up to 5 connections plus 10 temporary ones, fewer than the ~40 request threads. Requests hold a
  connection only for short queries, so contention stays low; a thread that finds no free connection waits up to
  30 s.
- SQLite limits: one writer at a time, and a local file that cannot be shared between hosts or replicas. WAL does
  not work on network file systems; the service then logs a warning and keeps SQLite's default journal mode.
  Scaling beyond one host means moving to PostgreSQL, where SQLAlchemy Core keeps most queries and Alembic would
  replace `PRAGMA user_version`.
- In Docker the cache lives in a named volume, so it survives restarts and rebuilds; `docker compose down -v`
  deletes it.
