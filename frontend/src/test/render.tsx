import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { createQueryClient } from "../api/queryClient";

/**
 * Render inside a fresh query client with the application's settings, so no cached response
 * leaks from one test into another. Returns the client to inspect the state of its queries.
 */
export function renderWithQueryClient(ui: ReactElement) {
  const client = createQueryClient();
  const result = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { ...result, client };
}
