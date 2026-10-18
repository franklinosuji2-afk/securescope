import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * These tests stub the API responses so the findings screens can be exercised with a known scan.
 * They check rendering and accessibility only; scanning itself is covered by the backend tests and
 * the real-backend tests in targets.e2e.ts.
 */
const user = {
  id: "u1",
  email: "analyst@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" },
  ],
};
function lifecycle(n: string, status = "open") {
  return {
    confidence: "high",
    fingerprint: n.repeat(32),
    status,
    status_note: null,
    first_seen_at: "2026-10-18T10:00:00Z",
    last_seen_at: "2026-10-18T10:00:00Z",
  };
}
const scan = {
  id: "abc123",
  target_url: "https://example.org/",
  host: "example.org",
  status: "completed",
  score: 76,
  grade: "C",
  created_at: "2026-10-18T10:00:00Z",
  finished_at: "2026-10-18T10:00:02Z",
  counts: { high: 1, medium: 1, low: 1, info: 1 },
  error: null,
  metadata: {
    requested_url: "https://example.org/",
    final_url: "https://example.org/",
    host: "example.org",
    resolved_addresses: ["93.184.216.34"],
    status_code: 200,
    content_type: "text/html",
    redirect_chain: [],
    off_origin_redirect: null,
    response_time_ms: 120,
    requests_made: 1,
    checks_run: ["https", "hsts", "csp"],
  },
  score_note: "Heuristic score.",
  findings: [
    {
      id: "SS-HDR-HSTS-001",
      title: "Strict-Transport-Security header is missing",
      severity: "high",
      category: "Security headers",
      description:
        "Without HSTS, browsers may still attempt plain HTTP connections.",
      evidence:
        "Strict-Transport-Security was not present. Checked the HTTP 200 response from https://example.org/.",
      remediation:
        "Send 'Strict-Transport-Security: max-age=31536000; includeSubDomains'.",
      ...lifecycle("1"),
    },
    {
      id: "SS-HDR-CSP-002",
      title: "Content-Security-Policy allows unsafe script execution",
      severity: "medium",
      category: "Security headers",
      description: "The policy permits 'unsafe-inline'.",
      evidence: "script-src 'self' 'unsafe-inline'",
      remediation: "Use nonces or hashes instead of 'unsafe-inline'.",
      ...lifecycle("2", "accepted_risk"),
    },
    {
      id: "SS-COOKIE-SAMESITE-001",
      title: "Cookies set without an explicit SameSite attribute",
      severity: "low",
      category: "Cookies",
      description: "Behaviour depends on the browser default.",
      evidence: "Cookie names: sid",
      remediation: "Set SameSite=Lax.",
      ...lifecycle("3"),
    },
    {
      id: "SS-DISC-SRV-002",
      title: "Server header is present",
      severity: "info",
      category: "Information disclosure",
      description: "The server announces its software name.",
      evidence: "Server: cloudflare",
      remediation: "Consider removing the Server header.",
      ...lifecycle("4", "resolved"),
    },
  ],
};

async function stubApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const body = url.endsWith("/auth/me")
      ? user
      : url.includes("/scans/abc123")
        ? scan
        : { items: [], total: 0 };
    await route.fulfill({ json: body });
  });
}

async function serious(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.passes.length).toBeGreaterThan(10);
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({
      id: v.id,
      nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
}

for (const scheme of ["dark", "light"] as const) {
  test(`findings list and detail are accessible (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stubApi(page);
    await page.goto("/#/findings?scan=abc123");
    await expect(page.getByRole("heading", { name: "Findings" })).toBeVisible();
    await expect(page.getByText("Showing 4 of 4 findings.")).toBeVisible();
    expect(await serious(page), `${scheme} list`).toEqual([]);
    await page.screenshot({
      path: `test-results/findings-list-${scheme}.png`,
      fullPage: true,
    });

    await page
      .getByRole("link", {
        name: /Strict-Transport-Security header is missing/,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Strict-Transport-Security header is missing",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "How to verify" }),
    ).toBeVisible();
    expect(await serious(page), `${scheme} detail`).toEqual([]);
    await page.screenshot({
      path: `test-results/finding-detail-${scheme}.png`,
      fullPage: true,
    });
  });
}

test("filters narrow the list and reset restores it", async ({ page }) => {
  await stubApi(page);
  await page.goto("/#/findings?scan=abc123");
  await page.getByRole("button", { name: /^Low/ }).click();
  await expect(page.getByText("Showing 1 of 4 findings.")).toBeVisible();
  await page.getByRole("button", { name: "Reset filters" }).click();
  await expect(page.getByText("Showing 4 of 4 findings.")).toBeVisible();
  await page.getByLabel("Search").fill("cookie");
  await expect(page.getByText("Showing 1 of 4 findings.")).toBeVisible();
});

test("findings are usable on a phone without sideways scrolling", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stubApi(page);
  await page.goto("/#/findings?scan=abc123");
  await expect(page.getByText("Showing 4 of 4 findings.")).toBeVisible();
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: "test-results/findings-mobile.png",
    fullPage: true,
  });
});

test("an analyst can change a finding's status from its page", async ({
  page,
}) => {
  await stubApi(page);
  const patches: unknown[] = [];
  await page.route("**/api/v1/findings/**", async (route) => {
    patches.push(route.request().postDataJSON());
    await route.fulfill({ status: 204 });
  });
  await page.goto("/#/findings?scan=abc123&finding=SS-HDR-HSTS-001");
  await page.getByLabel("Change status").selectOption("false_positive");
  await page.getByLabel("Note (optional)").fill("served by the CDN");
  await page.getByRole("button", { name: "Save status" }).click();
  await expect(page.getByText("Status saved.")).toBeVisible();
  expect(patches).toEqual([
    { status: "false_positive", note: "served by the CDN" },
  ]);
});

test("the status filter separates open, accepted and resolved findings", async ({
  page,
}) => {
  await stubApi(page);
  await page.goto("/#/findings?scan=abc123");
  await page.getByLabel("Status").selectOption("resolved");
  await expect(page.getByText("Showing 1 of 4 findings.")).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Server header is present/ }),
  ).toBeVisible();
});
