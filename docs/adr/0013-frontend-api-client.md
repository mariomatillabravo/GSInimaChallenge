# ADR-0013: API client and server state in the front-end

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

The front-end reads three endpoints: `/api/v1/meta` (options and limits), `/api/v1/stations` and the measurements.
It needs:

- types that follow the API contract, so a change in the API cannot silently break the page;
- errors that keep what the API says (code, message, parameter) and the `X-Request-ID`, so a user can report a
  failure and someone can find it in the logs;
- loading and error states, caching of data that does not change, and no requests piling up on a failing API, which
  already retries AEMET and stops calling it after a failure ([ADR-0010](0010-resilience.md)).

## Options considered

**Where the types come from**

1. **Generated from a committed copy of the OpenAPI document**: a script asks the application for its OpenAPI
   document, without a server or an API key, and writes `frontend/openapi.json`; openapi-typescript turns it into
   `frontend/src/api/schema.d.ts`. Both files are committed, and checks fail when either is out of date.
2. **Generated from the running API**: no generated files in the repository, but nothing reproducible to check in
   CI without starting the API.
3. **Generated during every build, not committed**: the front-end build would need Python and the backend.
4. **Written by hand**: they drift from the API without anyone noticing.

**HTTP client**

1. **A small wrapper over `fetch`**, typed with the generated types: about a hundred lines that build URLs, parse
   JSON and turn error answers into one error type.
2. **openapi-fetch**: less code, one more dependency, and the error handling and request ID would still be ours.
3. **axios**: a larger dependency for features (interceptors, upload progress) the page does not use.

**Server state**

1. **TanStack Query**: caching, request deduplication, cancellation, loading and error states, retry policy.
2. **`useEffect` + `fetch` by hand**: every component re-implements loading and error states, and fast changes can
   show the answer of an older request (race conditions).
3. **SWR**: similar and smaller, with less control over retries.

**Test doubles**

1. **Replace the global `fetch`** with a fake (`vi.stubGlobal`): the wrapper is the only caller of `fetch`.
2. **Mock Service Worker**: intercepts at the network level, one more tool to learn and configure.

## Decision

- **Types generated from the committed OpenAPI document** (option 1). `make api-types` regenerates both files.
  `make openapi-check` (backend CI job) fails when the API no longer matches `openapi.json`, and
  `make front-types-check` (front-end CI job) fails when the types no longer match `openapi.json`. Each check uses
  only its own toolchain, and the front-end builds without Python.
- **Own `fetch` wrapper** in `src/api/client.ts`. Query strings are built with `URLSearchParams`, which
  percent-encodes `+` as `%2B`. Any non-2xx answer becomes an `ApiError` with `status`, `code`, `message`,
  `parameter`, `requestId` and `retryAfterSeconds`; an answer without the API's JSON error body (for example the dev
  server's proxy when the API is down) becomes `api_unavailable`. A network failure stays the browser's `TypeError`,
  because nothing answered.
- **TanStack Query** with these defaults: no automatic refetch when the browser tab regains focus; `/meta` and
  `/stations` never go stale (they only change when the API restarts); **one retry after a network failure and none
  after an answer from the API**: a 4xx does not change by repeating it, and a 503 carries `Retry-After`.
- **Bodies are not validated at run time**: the types come from the schema the API itself publishes, and the drift
  checks keep them aligned. A validation library (such as Zod) would duplicate the schema.
- **Tests replace `fetch`** with a fake that answers by path, using fixtures copied from the API in demo mode and
  typed with the generated types.

## Consequences

- Changing the API contract means running `make api-types` and committing two generated files; forgetting it fails
  `make check` and CI with a message saying what to run.
- A contract change that breaks the front-end shows up as type errors in the front-end, including in the test
  fixtures.
- If something between the browser and the API returned a successful answer with an unexpected body, the page would
  fail when using it instead of at the boundary. The same origin and the proxy make that unlikely.
- Error messages can always show the request ID of the failed request.
