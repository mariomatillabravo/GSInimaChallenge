import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser only talks to its own origin and Vite forwards /api to the backend, so the API
// needs no CORS configuration and every response header (such as X-Request-ID) is readable.
// 127.0.0.1 instead of localhost: Node resolves localhost to the IPv6 address ::1 first, where
// uvicorn (bound to 127.0.0.1 by default) is not listening, so it would depend on the IPv4 fallback.
const apiProxy = { "/api": "http://127.0.0.1:8000" };

export default defineConfig({
  plugins: [react()],
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
