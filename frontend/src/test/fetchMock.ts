import { vi } from "vitest";

type Handler = (url: URL, init?: RequestInit) => { status?: number; body: unknown };

/** Replace global fetch with a router over path prefixes. Unknown paths return 404. */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.pathname === k || url.pathname.startsWith(k + "/") || url.pathname.startsWith(k + "?"));
    if (!key) return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
    const route = routes[key];
    const { status = 200, body } = typeof route === "function" ? (route as Handler)(url, init) : { body: route };
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
