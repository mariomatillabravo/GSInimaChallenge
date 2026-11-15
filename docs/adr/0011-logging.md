# ADR-0011: Structured logging with request IDs

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

The service now does work worth tracing: it fetches months from AEMET, serves stale copies, opens a circuit
breaker. When something goes wrong, an operator needs every line of one request, in a format a log platform can
parse, and a user needs something to quote in a bug report. Constraints:

- Endpoints are synchronous and run in a thread pool ([ADR-0007](0007-concurrency-model.md)), so a request's log
  lines are written from more than one thread.
- The AEMET API key must never reach the logs.
- Uvicorn writes its own startup and access lines in its own format.

## Options considered

**Library**

1. **Standard `logging` with a small JSON formatter of our own** (about 20 lines): no dependency, and every
   library's logs (Uvicorn, httpx) flow through the same handler.
2. **`structlog`**: a richer API, but a second logging system to configure next to the standard one, which the
   libraries keep using.
3. **`python-json-logger`**: only replaces the formatter we would write.

**Carrying the request ID to every line**

1. **A `ContextVar`** set by the request middleware. Synchronous endpoints run in worker threads that receive a
   copy of the request's context (verified in anyio's `run_sync_in_worker_thread`), so lines written from those
   threads carry the ID too.
2. **A thread-local variable**: set in the event loop's thread, it is invisible in the worker thread that runs the
   endpoint. A test shows the loss.
3. **Passing the ID explicitly** to every function: noisy, and impossible for library code.

**Access log**

1. **Our own access line**, written by the request middleware, with the request ID and structured HTTP fields;
   Uvicorn's access log is disabled and its other loggers are routed through our handler.
2. **Uvicorn's access log**: plain text even in JSON mode, without the request ID, and duplicated by ours.

**Request ID sent by the client**

1. **Reuse it when it is safe**: at most 128 characters of letters, digits, `.`, `_` and `-`; otherwise create a
   new one. Requests can be followed across services, and nobody can inject line breaks or fake entries.
2. **Always create one**: the safest, but the correlation with a caller is lost.
3. **Always reuse it**: opens the door to log injection.

**Timestamps**

1. **UTC with `Z`**: the server convention, consistent with UTC inside the service, and unambiguous during the
   autumn clock change.
2. **Madrid time**: friendlier, but one hour a year is ambiguous.

## Decision

Option 1 in every case.

- `app/core/logs.py` configures the root logger with one handler, in `text` or `json` (`LOG_FORMAT`) at
  `LOG_LEVEL`. It is called by the application factory and replaces its own handler when called again. JSON lines
  hold `time`, `level`, `logger`, `message`, `request_id`, any `extra` fields, and the traceback when there is one;
  values JSON cannot represent are written as text. Uvicorn's terminal colour copy of its messages is dropped.
- `app/api/middleware.py` is a plain ASGI middleware, the outermost of ours. It resolves the request ID, stores it
  in the `ContextVar` and in `request.state`, sets `X-Request-ID` on the response and writes the access line
  (method, path, query, status, duration). The value is not reset when the request ends: each request runs in its
  own task with its own copy of the context, and keeping it lets the handler of unexpected errors log it.
- Unexpected errors are answered by Starlette's outermost middleware, outside ours, so their handler adds
  `X-Request-ID` itself, taken from `request.state`.
- `httpx` and `httpcore` only log warnings. The API key travels in a request header, never in a URL, so even
  httpx's request lines (logged at `INFO` when enabled) do not contain it.
- Docker Compose sets `LOG_FORMAT=json`; running locally keeps `text`.

## Consequences

- One `grep` (or one filter on `request_id`) shows a whole request: the service's lines, failures, and its access
  line with status and duration.
- Every response, including a 500, carries the ID the user can quote; the front-end can show it with errors.
- Tests capture the real JSON output. They cover the formats, the ID rules, the ID in lines written by the
  endpoint thread, the access line, `X-Request-ID` on 404, 422 and 500 responses, and the absence of the API key
  in a full debug log of a real-mode request, httpx's request lines included (AEMET is simulated above
  `httpcore`, whose output that test therefore does not cover). Replacing the
  `ContextVar` with a thread-local variable, or removing the header from the 500 handler, makes them fail.
- The Docker healthcheck adds one access line every 30 seconds.
