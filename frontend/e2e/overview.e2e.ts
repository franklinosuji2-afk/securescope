import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Stubbed API: checks how the Overview reads in each state, and its accessibility, in both themes. */
const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [{ id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" }],
};

const target = (hostname: string, status: "pending" | "verified") => ({
  id: hostname,
  hostname,
  status,
  challenge_token: "a".repeat(32),
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: status === "verified" ? "2026-10-18T10:00:00Z" : null,
  verification_method: status === "verified" ? "dns_txt" : null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: `_securescope-challenge.${hostname}`,
  dns_record_value: "securescope-verification=" + "a".repeat(32),
  http_file_url: `https://${hostname}/.well-known/securescope-verification.txt`,
  http_file_content: "securescope-verification=" + "a".repeat(32),
});

function summary(id: string, host: string, created: string, score: number, grade: string, counts: object) {
  return { id, target_url: `https://${host}/`, host, status: "completed", score, grade, created_at: created, finished_at: created, counts };
}

const finding = (id: string, title: string, severity: string, n: string, status = "open") => ({
  id,
  title,
  severity,
  category: "Security headers",
  description: "d",
  evidence: "e",
  remediation: "Send the header.",
  confidence: "high",
  fingerprint: n.repeat(32),
  status,
  status_note: null,
  first_seen_at: "2026-10-18T10:00:00Z",
  last_seen_at: "2026-10-18T12:00:00Z",
});

const latestExample = {
  ...summary("s2", "example.org", "2026-10-18T12:00:00Z", 84, "B", { high: 1, low: 1 }),
  error: null,
  metadata: null,
  score_note: "Heuristic score.",
  findings: [
    finding("SS-HDR-HSTS-001", "Strict-Transport-Security header is missing", "high", "1"),
    finding("SS-COOKIE-SAMESITE-001", "Cookies set without an explicit SameSite attribute", "low", "2"),
    finding("SS-HDR-CSP-002", "Content-Security-Policy allows unsafe script execution", "medium", "3", "resolved"),
  ],
};

async function stub(page: Page, state: "new" | "verified" | "scanned") {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { items: [], total: 0 };
    if (url.endsWith("/auth/me")) body = user;
    else if (url.includes("/targets")) {
      body = {
        items:
          state === "new" ? [] : state === "verified" ? [target("example.org", "verified")] : [target("example.org", "verified"), target("staging.example.org", "pending")],
      };
    } else if (url.includes("/scans/s2")) body = latestExample;
    else if (url.includes("/scans") && state === "scanned") {
      body = {
        total: 2,
        items: [
          summary("s2", "example.org", "2026-10-18T12:00:00Z", 84, "B", { high: 1, low: 1 }),
          summary("s1", "example.org", "2026-10-18T10:00:00Z", 76, "C", { high: 1, medium: 1, low: 1 }),
        ],
      };
    }
    await route.fulfill({ json: body });
  });
}

async function serious(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.passes.length).toBeGreaterThan(10);
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
}

for (const scheme of ["dark", "light"] as const) {
  test(`new account: guided setup is clear and accessible (${scheme} theme)`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "new");
    await page.goto("/#/");
    await expect(page.getByRole("heading", { name: "Get your first result" })).toBeVisible();
    await expect(page.locator("li[aria-current=step]")).toContainText("Add the site you want to check");
    expect(await serious(page), `${scheme} guide`).toEqual([]);
    await page.screenshot({ path: `test-results/overview-new-${scheme}.png`, fullPage: true });
  });

  test(`scanned account: fix-first and site cards are accurate and accessible (${scheme} theme)`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "scanned");
    await page.goto("/#/");
    await expect(page.getByRole("heading", { name: "Fix this first" })).toBeVisible();
    // High outranks low; the resolved CSP finding is not offered.
    await expect(page.getByText("Strict-Transport-Security header is missing").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Get your first result" })).toHaveCount(0);
    const card = page.getByRole("listitem", { name: "example.org" });
    await expect(card).toContainText("84");
    await expect(card).toContainText("Up 8 since the previous scan");
    await expect(card).toContainText("2 open");
    expect(await serious(page), `${scheme} posture`).toEqual([]);
    await page.screenshot({ path: `test-results/overview-scanned-${scheme}.png`, fullPage: true });
  });
}

test("verified sites fill the scan form, and the fix link opens the finding", async ({ page }) => {
  await stub(page, "scanned");
  await page.goto("/#/");
  await page.getByRole("button", { name: "example.org" }).click();
  await expect(page.getByLabel("Target URL")).toHaveValue("https://example.org/");
  await page.getByRole("link", { name: "See the evidence and fix" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Strict-Transport-Security header is missing" })).toBeVisible();
});

test("overview does not scroll sideways on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stub(page, "scanned");
  await page.goto("/#/");
  await expect(page.getByRole("heading", { name: "Fix this first" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
