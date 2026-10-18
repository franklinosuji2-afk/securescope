import { useCallback, useEffect, useState } from "react";

export type Page =
  | "overview"
  | "targets"
  | "findings"
  | "history"
  | "team"
  | "login"
  | "register"
  | "forgot-password"
  | "reset-password"
  | "verify-email";

const PAGES: readonly Page[] = [
  "targets",
  "findings",
  "history",
  "team",
  "login",
  "register",
  "forgot-password",
  "reset-password",
  "verify-email",
];
export const PUBLIC_PAGES: readonly Page[] = [
  "login",
  "register",
  "forgot-password",
  "reset-password",
  "verify-email",
];
export interface Route {
  page: Page;
  scanId: string | null;
  token: string | null;
}

export function parseHash(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  const raw = params.get("scan");
  const scanId = raw && /^[A-Za-z0-9]{1,64}$/.test(raw) ? raw : null;
  const name = path.replace(/^\//, "");
  const page: Page = (PAGES as readonly string[]).includes(name) ? (name as Page) : "overview";
  const rawToken = params.get("token");
  const token = rawToken && /^[A-Za-z0-9_-]{10,200}$/.test(rawToken) ? rawToken : null;
  return { page, scanId, token };
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
