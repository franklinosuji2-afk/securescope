import type { Page } from "./router";

const SUFFIX = "SecureScope";

/** The default title, also used on the public home page. Kept in step with index.html. */
export const DEFAULT_TITLE = "SecureScope: website security checks";

/**
 * What each page is called in the browser tab, history and bookmarks. Pages that set their own title
 * (the sample report, the agency page and shared reports) are not listed.
 */
const TITLES: Partial<Record<Page, string>> = {
  overview: "Overview",
  "not-found": "Page not found",
  targets: "Targets",
  integrations: "Integrations",
  findings: "Findings",
  history: "Scan history",
  team: "Team",
  account: "Account",
  audit: "Audit log",
  analytics: "Analytics",
  health: "Platform health",
  login: "Sign in",
  register: "Create your account",
  "forgot-password": "Reset your password",
  "reset-password": "Choose a new password",
  "verify-email": "Confirm your email",
  "accept-invite": "Join a workspace",
  clients: "Clients",
  "app-scanning": "App Scanning",
  compare: "Compare scans",
  impressum: "Impressum",
  privacy: "Privacy notice",
  terms: "Terms of use",
  checks: "What we check",
  pricing: "Pricing",
  help: "Help",
  "early-access": "App Scanning (Early Access)",
};

/** Pages that manage `document.title` themselves. */
export const SELF_TITLED: readonly Page[] = [
  "sample-report",
  "agency-features",
  "shared",
];

/** The tab title for a page, or null when the page sets its own. */
export function titleFor(page: Page, signedIn: boolean): string | null {
  if (SELF_TITLED.includes(page)) return null;
  // Visitors who are not signed in see the public home page at the same address.
  if (page === "overview" && !signedIn) return DEFAULT_TITLE;
  const label = TITLES[page];
  return label ? `${label} – ${SUFFIX}` : DEFAULT_TITLE;
}
