import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Website analytics and Platform health with data in them: readable, accessible, no sideways scroll. */
const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  is_admin: true,
  organizations: [
    { id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" },
  ],
};

const series = Array.from({ length: 30 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 8, 22 + i));
  const visitors = [3, 5, 2, 8, 6, 4, 9, 7, 12, 5][i % 10] + (i % 4);
  return {
    date: d.toISOString().slice(0, 10),
    visitors,
    views: visitors * 2 + (i % 3),
  };
});

const analytics = {
  range_days: 30,
  timezone: "UTC",
  tracking_enabled: true,
  last_event_at: "2026-10-20T10:00:00Z",
  current: { views: 410, visitors: 190, series },
  previous: { views: 300, visitors: 150, series: [] },
  today: { views: 18, visitors: 9 },
  yesterday: { views: 22, visitors: 11 },
  top_pages: [
    { name: "login", count: 120, visitors: 80 },
    { name: "register", count: 60, visitors: 40 },
    { name: "privacy", count: 20, visitors: 18 },
  ],
  landing_pages: [
    { name: "login", count: 90 },
    { name: "home", count: 30 },
  ],
  sources: [
    { name: "Direct", count: 100 },
    { name: "github.com", count: 40 },
  ],
  devices: [
    { name: "desktop", count: 150 },
    { name: "mobile", count: 40 },
  ],
};

const health = {
  version: "0.8.0",
  started_at: "2026-10-20T10:00:00Z",
  uptime_seconds: 93700,
  database: { ok: true, latency_ms: 12 },
  requests: {
    window_seconds: 3600,
    requests: 240,
    server_errors: 2,
    client_errors: 9,
    error_rate: 0.008,
    p50_ms: 42,
    p95_ms: 180,
    p99_ms: 410,
    routes: [
      { route: "/api/v1/scans", requests: 90, errors: 0, p95_ms: 200 },
      { route: "/api/v1/targets", requests: 60, errors: 1, p95_ms: 90 },
    ],
    truncated: false,
  },
  scans: {
    window_hours: 24,
    completed: 14,
    failed: 2,
    cancelled: 1,
    in_progress: 1,
    avg_seconds: 4.2,
    max_concurrent: 3,
    running_here: 1,
  },
  mail: {
    provider: "brevo",
    delivering: true,
    sent: 25,
    failed: 1,
    last_success_at: "2026-10-20T12:00:00Z",
    last_failure_at: null,
    last_failure_status: null,
  },
  configuration: {
    trusted_proxy: true,
    admin_email: true,
    analytics_enabled: true,
    metrics_endpoint: false,
    cookie_secure: true,
    verification_valid_days: 180,
    retention_days: 30,
  },
};

async function stub(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const json = (body: unknown) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (url.endsWith("/auth/me")) return json(user);
    if (url.includes("/analytics/summary")) return json(analytics);
    if (url.endsWith("/platform/health")) return json(health);
    return json({ items: [], sites: [], fix_first: null });
  });
}

for (const scheme of ["dark", "light"] as const) {
  for (const [name, path] of [
    ["analytics", "/#/analytics"],
    ["health", "/#/health"],
  ] as const) {
    test(`${name} dashboard is accessible and fits the screen (${scheme})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.emulateMedia({ colorScheme: scheme });
      await stub(page);
      await page.goto(path);
      await expect(page.locator(".kpi").first()).toBeVisible();
      if (process.env.SHOTS)
        await page.screenshot({
          path: `${process.env.SHOTS}/${name}-${scheme}.png`,
          fullPage: true,
        });
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
      for (const width of [390, 768]) {
        await page.setViewportSize({ width, height: 900 });
        const overflow = await page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        );
        expect(overflow).toBeLessThanOrEqual(0);
      }
    });
  }
}
