import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "../test/fetch";
import { ApiError } from "./client";
import { useMeta } from "./queries";
import { createQueryClient, shouldRetry } from "./queryClient";

const apiError = new ApiError({
  status: 503,
  code: "upstream_unavailable",
  message: "AEMET failed recently.",
  parameter: null,
  requestId: "r-1",
  retryAfterSeconds: 60,
});

describe("shouldRetry", () => {
  it("never retries an answer from the API", () => {
    expect(shouldRetry(0, apiError)).toBe(false);
  });

  it("retries a network failure once", () => {
    expect(shouldRetry(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetry(1, new TypeError("Failed to fetch"))).toBe(false);
  });
});

describe("query client", () => {
  /** Runs useMeta with the application's settings, without waiting between attempts. */
  async function attemptsUntilError(answer: () => Response): Promise<number> {
    const fake = stubFetch({ "/api/v1/meta": answer });
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, retryDelay: 0 } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useMeta(), { wrapper });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    return fake.mock.calls.length;
  }

  it("makes two attempts when the network fails", async () => {
    const attempts = await attemptsUntilError(() => {
      throw new TypeError("Failed to fetch");
    });

    expect(attempts).toBe(2);
  });

  it("makes a single attempt when the API answers with an error", async () => {
    const attempts = await attemptsUntilError(() =>
      jsonResponse(
        { error: { code: "upstream_unavailable", message: "Down.", parameter: null } },
        { status: 503 },
      ),
    );

    expect(attempts).toBe(1);
  });
});
