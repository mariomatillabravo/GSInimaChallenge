import { vi } from "vitest";

export function jsonResponse(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

/**
 * Replace the global fetch with a fake that answers each path with a fresh response (a response
 * body can only be read once); a route may return a promise that never settles, to keep a request
 * in flight. Requests to other paths fail the test. Vitest restores the real fetch after each
 * test (unstubGlobals in vite.config.ts).
 */
export function stubFetch(routes: Record<string, () => Response | Promise<Response>>) {
  const fake = vi.fn((url: string) => {
    const path = url.split("?")[0] ?? url;
    const route = routes[path];
    return route === undefined
      ? Promise.reject(new Error(`Unexpected request: ${url}`))
      : Promise.resolve(route());
  });
  vi.stubGlobal("fetch", fake);
  return fake;
}
