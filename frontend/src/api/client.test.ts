import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "../test/fetch";
import { demoMeta } from "../test/fixtures";
import { ApiError, buildUrl, fetchMeasurements, fetchMeta, measurementsUrl } from "./client";

const MEASUREMENTS = "/api/v1/stations/juan-carlos-i/measurements";

describe("buildUrl", () => {
  it("percent-encodes a plus sign, so the API does not read it as a space", () => {
    expect(buildUrl("/x", { tz: "+02:00" })).toBe("/x?tz=%2B02%3A00");
  });

  it("repeats list parameters and leaves out missing values", () => {
    expect(buildUrl("/x", { types: ["temperature", "speed"], tz: null, format: undefined })).toBe(
      "/x?types=temperature&types=speed",
    );
  });

  it("returns the bare path without parameters", () => {
    expect(buildUrl("/x")).toBe("/x");
  });
});

describe("measurementsUrl", () => {
  it("builds the measurements URL of a station", () => {
    const url = measurementsUrl("juan-carlos-i", {
      start: "2025-03-30T00:00:00",
      end: "2025-03-31T00:00:00",
      aggregation: "hourly",
      types: ["temperature"],
    });

    expect(url).toBe(
      `${MEASUREMENTS}?start=2025-03-30T00%3A00%3A00&end=2025-03-31T00%3A00%3A00` +
        "&aggregation=hourly&types=temperature",
    );
  });

  it("encodes the station identifier as a single path segment", () => {
    expect(measurementsUrl("a/b", { start: "s", end: "e" })).toMatch(
      /^\/api\/v1\/stations\/a%2Fb\/measurements\?/,
    );
  });
});

describe("fetchMeta", () => {
  it("returns the parsed body of a successful answer", async () => {
    const fake = stubFetch({ "/api/v1/meta": () => jsonResponse(demoMeta) });

    await expect(fetchMeta()).resolves.toEqual(demoMeta);
    expect(fake).toHaveBeenCalledWith("/api/v1/meta", expect.anything());
  });
});

describe("errors", () => {
  const query = { start: "2025-03-30T02:30:00", end: "2025-03-31T00:00:00" };

  it("turns an error body into an ApiError with the request ID", async () => {
    stubFetch({
      [MEASUREMENTS]: () =>
        jsonResponse(
          {
            error: {
              code: "invalid_parameter",
              message: "'2025-03-30T02:30:00' does not exist in Europe/Madrid.",
              parameter: "start",
            },
          },
          { status: 422, headers: { "X-Request-ID": "a867d84a9a504f289d7cce6fbe8599ea" } },
        ),
    });

    const error = await fetchMeasurements("juan-carlos-i", query).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "invalid_parameter",
      message: "'2025-03-30T02:30:00' does not exist in Europe/Madrid.",
      parameter: "start",
      requestId: "a867d84a9a504f289d7cce6fbe8599ea",
      retryAfterSeconds: null,
    });
  });

  it("reads Retry-After from a 503", async () => {
    stubFetch({
      [MEASUREMENTS]: () =>
        jsonResponse(
          {
            error: {
              code: "upstream_unavailable",
              message: "AEMET failed recently and is not being called for a while.",
              parameter: null,
            },
          },
          { status: 503, headers: { "Retry-After": "42", "X-Request-ID": "r-503" } },
        ),
    });

    await expect(fetchMeasurements("juan-carlos-i", query)).rejects.toMatchObject({
      status: 503,
      code: "upstream_unavailable",
      retryAfterSeconds: 42,
    });
  });

  it("explains an answer without an error body, such as the proxy's when the API is down", async () => {
    stubFetch({ "/api/v1/meta": () => new Response("", { status: 502 }) });

    await expect(fetchMeta()).rejects.toMatchObject({
      status: 502,
      code: "api_unavailable",
      message: "The API did not answer (HTTP 502). Check that it is running.",
      requestId: null,
    });
  });

  it("lets a network failure through as it is, since nothing answered", async () => {
    stubFetch({
      "/api/v1/meta": () => {
        throw new TypeError("Failed to fetch");
      },
    });

    const error = await fetchMeta().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(TypeError);
    expect(error).not.toBeInstanceOf(ApiError);
  });
});
