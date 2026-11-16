import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createQueryClient } from "./api/queryClient";
import { App } from "./App";
import "./styles/global.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("The #root element is missing from index.html.");
}

// One client for the whole page: it holds the cache of every API response.
const queryClient = createQueryClient();

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
