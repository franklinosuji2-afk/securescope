import { useCallback, useEffect, useState } from "react";

export type Page =
  | "overview"
  | "not-found"
  | "targets"
  | "findings"
  | "history"
  | "team"
  | "account"
  | "audit"
  | "analytics"
  | "health"
  | "login"
  | "register"
  | "forgot-password"
  | "reset-password"
  | "verify-email"
  | "accept-invite"
  | "sample-report"
  | "impressum"
  | "privacy"
  | "terms";

const PAGES: readonly Page[] = [
  "targets",
  "findings",
  "history",
  "team",
  "account",
  "audit",
  "analytics",
  "health",
  "login",
  "register",
  "forgot-password",
  "reset-password",
  "verify-email",
  "accept-invite",
  "sample-report",
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
  "accept-invite",
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
  // An empty path is the home page; a name we do not know is shown as "not found" instead of silently
  // landing on Overview.
  const page: Page = (PAGES as readonly string[]).includes(name)
    ? (name as Page)
    : name === "" || name === "overview"
      ? "overview"
      : "not-found";
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
    const hash = buildHash(page, scanId);
    window.location.hash = hash;
    // At once, not on the later hashchange event, so a change made alongside it (such as switching
    // organization) renders together with the new route.
    setRoute(parseHash(hash));
  }, []);
  return [route, navigate];
}

const OAUTH_ERRORS = [
  "failed",
  "cancelled",
  "email_unverified",
  "disabled",
  "unavailable",
] as const;
export type OAuthErrorCode = (typeof OAUTH_ERRORS)[number];

/** The reason the server gives when a Google or GitHub sign-in did not work, from `#/login?oauth_error=...`. */
export function parseOAuthError(hash: string): OAuthErrorCode | null {
  const query = hash.replace(/^#/, "").split("?")[1] ?? "";
  const value = new URLSearchParams(query).get("oauth_error");
  return (OAUTH_ERRORS as readonly string[]).includes(value ?? "")
    ? (value as OAuthErrorCode)
    : null;
}
