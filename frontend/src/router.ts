import { useCallback, useEffect, useState } from "react";

export type Page =
  | "overview"
  | "targets"
  | "findings"
  | "history"
  | "team"
  | "audit"
  | "login"
  | "register"
  | "forgot-password"
  | "reset-password"
  | "verify-email"
  | "impressum"
  | "privacy"
  | "terms";

const PAGES: readonly Page[] = [
  "targets",
  "findings",
  "history",
  "team",
  "audit",
  "login",
  "register",
  "forgot-password",
  "reset-password",
  "verify-email",
  "impressum",
  "privacy",
  "terms",
];
export const LEGAL_PAGES: readonly Page[] = ["impressum", "privacy", "terms"];
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
  findingId: string | null;
  token: string | null;
}

export function parseHash(hash: string): Route {
  const [path = "", query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  const raw = params.get("scan");
  const scanId = raw && /^[A-Za-z0-9]{1,64}$/.test(raw) ? raw : null;
  const name = path.replace(/^\//, "");
  const page: Page = (PAGES as readonly string[]).includes(name)
    ? (name as Page)
    : "overview";
  const rawFinding = params.get("finding");
  const findingId =
    rawFinding && /^[A-Za-z0-9-]{1,64}$/.test(rawFinding) ? rawFinding : null;
  const rawToken = params.get("token");
  const token =
    rawToken && /^[A-Za-z0-9_-]{10,200}$/.test(rawToken) ? rawToken : null;
  return { page, scanId, findingId, token };
}

export function buildHash(
  page: Page,
  scanId: string | null,
  findingId: string | null = null,
): string {
  const path = page === "overview" ? "/" : `/${page}`;
  if (!scanId) return `#${path}`;
  return findingId
    ? `#${path}?scan=${scanId}&finding=${findingId}`
    : `#${path}?scan=${scanId}`;
}

export function useRoute(): [
  Route,
  (page: Page, scanId?: string | null) => void,
] {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(window.location.hash),
  );
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
