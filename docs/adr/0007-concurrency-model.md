# ADR-0007: Synchronous request handling

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

FastAPI runs `async def` endpoints on a single-threaded event loop, which switches between requests whenever one
awaits I/O, and runs plain `def` endpoints in a thread pool. Serving a request here involves three steps:

- reading the SQLite cache: blocking, as the standard `sqlite3` module is synchronous;
- calling AEMET when data is missing: network I/O;
- aggregating with pandas: CPU work, also blocking.

Blocking code inside an `async def` endpoint freezes the event loop, and with it every other request.

## Options considered

1. **Fully synchronous**: `def` endpoints, `httpx.Client` and synchronous SQLAlchemy. Each blocking call happens in
   a pool thread and only holds up its own request.
2. **Fully asynchronous**: `async def` endpoints, `httpx.AsyncClient`, async SQLAlchemy with `aiosqlite`, and
   pandas sent to a worker thread with `run_in_threadpool`. Correct as well, but with more moving parts, and any
   blocking call slipped in by mistake stalls the whole service. `aiosqlite` itself runs SQLite in a background
   thread.
3. **Mixed** (`async def` endpoints calling blocking code directly): a common mistake, not a real option.

## Decision

**Option 1, fully synchronous.** It is correct by construction and simpler to read, test and debug. The real
bottlenecks are SQLite's single writer and AEMET's rate limits, not the number of threads, and the cache will make
most requests short reads. CPU-bound work scales with processes, not threads or coroutines, in any of the options.

## Consequences

- Endpoints are `def`. The few `async` functions (the application lifespan and the exception handlers) do no
  blocking work.
- Concurrency per process is bounded by the thread pool (about 40 threads by default); scaling out means more
  worker processes or replicas.
- If streaming or many slow upstream calls ever became the norm, moving to async would be contained in the client
  and repository layers.
