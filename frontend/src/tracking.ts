import type { Page } from "./router";

/**
 * Cookieless visit counting for the public pages only.
 *
 * What is sent: the page name and, on the first view, the site that linked here. Nothing is stored in
 * the browser, no cookie is set and no identifier is created. The server adds a coarse device class and
 * a one-way hash that changes daily. Browsers that send Do Not Track or Global Privacy Control are not
 * counted at all.
 */
const COUNTED: Partial<Record<Page, string>> = {
  overview: "home",
  login: "login",
  register: "register",
  "forgot-password": "forgot-password",
  "reset-password": "reset-password",
  "verify-email": "verify-email",
  "sample-report": "sample-report",
  impressum: "impressum",
  privacy: "privacy",
  terms: "terms",
};

export function trackedPageName(page: Page): string | null {
  return COUNTED[page] ?? null;
}

function optedOut(): boolean {
  const nav = navigator as Navigator & {
    globalPrivacyControl?: boolean;
    msDoNotTrack?: string;
  };
  return (
    nav.doNotTrack === "1" ||
    nav.msDoNotTrack === "1" ||
    nav.globalPrivacyControl === true
  );
}

let firstView = true;

export function trackPageView(page: string): void {
  if (optedOut()) return;
  const referrer = firstView && document.referrer ? document.referrer : null;
  firstView = false;
  try {
    void fetch("/api/v1/analytics/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(referrer ? { page, referrer } : { page }),
      credentials: "omit",
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // Counting must never affect the page.
  }
}
