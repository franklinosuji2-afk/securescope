import { useCallback, useEffect, useState } from "react";

export type Page = "overview" | "findings" | "history";
export interface Route {
  page: Page;
  scanId: string | null;
}

export function parseHash(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  const raw = params.get("scan");
  const scanId = raw && /^[A-Za-z0-9]{1,64}$/.test(raw) ? raw : null;
  const page: Page = path === "/findings" ? "findings" : path === "/history" ? "history" : "overview";
  return { page, scanId };
}

export function buildHash(page: Page, scanId: string | null): string {
  const path = page === "overview" ? "/" : `/${page}`;
  return scanId ? `#${path}?scan=${scanId}` : `#${path}`;
}

export function useRoute(): [Route, (page: Page, scanId?: string | null) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const navigate = useCallback((page: Page, scanId: string | null = null) => {
    window.location.hash = buildHash(page, scanId);
  }, []);
  return [route, navigate];
}
