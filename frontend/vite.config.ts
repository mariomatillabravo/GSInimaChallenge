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
    // Undo vi.stubGlobal (used to replace fetch) after every test.
    unstubGlobals: true,
    // The first test that shows a result loads the charts' chunk (Recharts), which jsdom and the
    // transform take a few seconds to import; the 5-second default made it fail on a busy machine.
    testTimeout: 15_000,
    // `npm run coverage`: a report without a threshold (the backend has one).
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/api/schema.d.ts", "src/main.tsx"],
    },
  },
});
