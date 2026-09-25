import { useEffect, useState } from "react";

export type Route = { view: string; params: URLSearchParams };

function parse(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [view, query = ""] = hash.split("?");
  return { view: view || "ask", params: new URLSearchParams(query) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function href(view: string, params: Record<string, string | undefined> = {}): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v && p.set(k, v));
  const q = p.toString();
  return `#/${view}${q ? `?${q}` : ""}`;
}

export function navigate(view: string, params: Record<string, string | undefined> = {}) {
  window.location.hash = href(view, params);
}
