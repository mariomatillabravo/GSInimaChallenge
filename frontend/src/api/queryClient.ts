import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./client";

/**
 * Retry once after a network failure, never after an answer from the API: the API already
 * retries AEMET and stops calling it after a failure, a 4xx does not change by repeating it, and
 * a 503 says when to try again (Retry-After).
 *
 * TanStack Query passes the number of failures before the current one: 0 on the first failure.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  return !(error instanceof ApiError) && failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        // Data does not change because the user switched tabs; a new query is an explicit action.
        refetchOnWindowFocus: false,
      },
    },
  });
}
