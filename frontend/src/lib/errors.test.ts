import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { describeError } from "./errors";

describe("describeError", () => {
  it("shows the API's own message", () => {
    const error = new ApiError({
      status: 503,
      code: "upstream_unavailable",
      message:
        "AEMET failed recently and is not being called for a while. Try again in 42 seconds.",
      parameter: null,
      requestId: "r-1",
      retryAfterSeconds: 42,
    });

    expect(describeError(error)).toBe(error.message);
  });

  it("explains a request that got no answer at all", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toBe(
      "Cannot reach the API. Check your connection and that the API is running.",
    );
  });
});
