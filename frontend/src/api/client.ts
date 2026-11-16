/**
 * Typed access to the API.
 *
 * Every call goes to a relative URL (/api/...), served by the same origin as the page, so the
 * browser never makes a cross-origin request (see vite.config.ts). The types come from
 * schema.d.ts, generated from the API's OpenAPI document: if the API contract changes, the
 * compiler points at every place that must change too.
 */
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type MetaResponse = Schemas["MetaResponse"];
export type Station = Schemas["StationOut"];
export type TimeSpan = Schemas["TimeSpanOut"];
export type MeasurementsResponse = Schemas["MeasurementsResponse"];
export type MeasurementsQuery =
  paths["/api/v1/stations/{station_id}/measurements"]["get"]["parameters"]["query"];
type ErrorBody = Schemas["ErrorResponse"];

/** A failed answer from the API (any status other than 2xx). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  /** The query parameter that caused the error, when there is one. */
  readonly parameter: string | null;
  /** The X-Request-ID header: lets anyone find the matching lines in the API logs. */
  readonly requestId: string | null;
  /** From Retry-After, sent with 503 while the API is not calling AEMET. */
  readonly retryAfterSeconds: number | null;

  constructor(details: {
    status: number;
    code: string;
    message: string;
    parameter: string | null;
    requestId: string | null;
    retryAfterSeconds: number | null;
  }) {
    super(details.message);
    this.name = "ApiError";
    this.status = details.status;
    this.code = details.code;
    this.parameter = details.parameter;
    this.requestId = details.requestId;
    this.retryAfterSeconds = details.retryAfterSeconds;
  }
}

type QueryValue = string | readonly string[] | null | undefined;

/**
 * Append the query parameters to a path. Lists become repeated parameters (types=a&types=b),
 * and null or undefined values are left out. URLSearchParams percent-encodes every reserved
 * character: a "+" in a UTC offset is sent as %2B, so the API does not read it as a space.
 */
export function buildUrl(path: string, query: Readonly<Record<string, QueryValue>> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) {
      continue;
    }
    for (const item of typeof value === "string" ? [value] : value) {
      params.append(key, item);
    }
  }
  const search = params.toString();
  return search === "" ? path : `${path}?${search}`;
}

export function fetchMeta(signal?: AbortSignal): Promise<MetaResponse> {
  return getJson("/api/v1/meta", signal);
}

export function fetchStations(signal?: AbortSignal): Promise<Station[]> {
  return getJson("/api/v1/stations", signal);
}

/** Also used as the CSV download link, with format=csv. */
export function measurementsUrl(stationId: string, query: MeasurementsQuery): string {
  return buildUrl(`/api/v1/stations/${encodeURIComponent(stationId)}/measurements`, query);
}

export function fetchMeasurements(
  stationId: string,
  query: MeasurementsQuery,
  signal?: AbortSignal,
): Promise<MeasurementsResponse> {
  return getJson(measurementsUrl(stationId, query), signal);
}

/**
 * GET a JSON resource. The body is trusted to match the generated type, because the API itself
 * produces the schema the types come from; it is not validated again at run time.
 *
 * A network failure (API or proxy unreachable) rejects with the browser's TypeError, not with
 * ApiError: nothing answered.
 */
async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  const common = {
    status: response.status,
    requestId: response.headers.get("X-Request-ID"),
    retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
  };
  const body: unknown = await response.json().catch(() => null);
  if (isErrorBody(body)) {
    const { code, message, parameter } = body.error;
    return new ApiError({ ...common, code, message, parameter: parameter ?? null });
  }
  // Every error of the API has a JSON body; any other answer comes from something in between,
  // such as the dev server's proxy when the API is not running.
  return new ApiError({
    ...common,
    code: "api_unavailable",
    message: `The API did not answer (HTTP ${String(response.status)}). Check that it is running.`,
    parameter: null,
  });
}

/** The API sends Retry-After as a number of seconds. */
function parseRetryAfter(value: string | null): number | null {
  if (value === null) {
    return null;
  }
  const seconds = Number.parseInt(value, 10);
  return Number.isNaN(seconds) ? null : seconds;
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) {
    return false;
  }
  const { error } = value;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
}
