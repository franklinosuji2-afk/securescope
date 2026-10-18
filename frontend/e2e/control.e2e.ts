import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { register, uniqueEmail } from "./helpers";

/** Stubbed API: the audit log, cancelling and retrying, in both themes, with accessibility checks. */
const owner = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [{ id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" }],
};
const viewer = { ...owner, organizations: [{ ...owner.organizations[0], role: "VIEWER" }] };

const scan = (id: string, status: string) => ({
  id,
  target_url: "https://example.org/",
  host: "example.org",
  status,
  score: null,
  grade: null,
  created_at: "2026-10-18T12:00:00Z",
  finished_at: status === "running" ? null : "2026-10-18T12:00:03Z",
  counts: {},
  error: status === "failed" ? "The connection timed out." : status === "cancelled" ? "Cancelled before it finished." : null,
  metadata: null,
  findings: [],
  score_note: "Heuristic score.",
});

const event = (n: number, type: string, actor: string | null, resource: [string, string] | null) => ({
  id: `e${n}`,
  timestamp: `2026-10-18T1${n % 10}:00:00Z`,
  event_type: type,
  actor_user_id: actor ? "u1" : null,
  actor_email: actor,
  resource_type: resource?.[0] ?? null,
  resource_id: resource?.[1] ?? null,
  request_id: n % 2 ? "9f8e7d6c5b4a39281716" : null,
});

const audit = {
  items: [
    event(1, "scan.cancelled", "owner@example.org", ["scan", "abcdef1234567890abcdef1234567890"]),
    event(2, "report.exported", "owner@example.org", ["scan", "abcdef1234567890abcdef1234567890"]),
    event(3, "org.member.added", "owner@example.org", ["user", "0123456789abcdef0123456789abcdef"]),
    event(4, "target.verified", "owner@example.org", ["target", "fedcba9876543210fedcba9876543210"]),
    event(5, "auth.login.failed", null, null),
  ],
  total: 5,
  event_types: ["auth.login.failed", "org.member.added", "report.exported", "scan.cancelled", "target.verified"],
};

async function stub(page: Page, scanStatus: string, me = owner) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { items: [], total: 0 };
    if (url.endsWith("/auth/me")) body = me;
    else if (url.includes("/audit-events")) body = audit;
    else if (url.includes("/overview")) body = { sites: [], fix_first: null, other_open: 0 };
    else if (url.includes("/scans/s1")) body = scan("s1", scanStatus);
    else if (url.includes("/scans?")) {
      body = { items: ["running", "failed", "cancelled", "completed"].map((s, i) => scan(`h${i}`, s)), total: 4 };
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
  test(`audit log is readable and accessible (${scheme} theme)`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "completed");
    await page.goto("/#/audit");
    await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
    const table = page.getByRole("table");
    await expect(table.getByRole("row")).toHaveCount(6); // header + 5 events
    await expect(table).toContainText("Scan cancelled");
    await expect(table).toContainText("Failed sign-in");
    await expect(table).toContainText("No user recorded");
    expect(await serious(page), `${scheme} audit`).toEqual([]);
    await page.screenshot({ path: `test-results/audit-${scheme}.png`, fullPage: true });
  });

  test(`a running scan can be cancelled and a failed one retried, accessibly (${scheme} theme)`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "running");
    await page.goto("/#/?scan=s1");
    await expect(page.getByRole("button", { name: "Cancel scan" })).toBeVisible();
    expect(await serious(page), `${scheme} running`).toEqual([]);

    await page.unroute("**/api/v1/**");
    await stub(page, "failed");
    await page.goto("/#/?scan=s1");
    await page.reload();
    await expect(page.getByRole("button", { name: "Retry scan" })).toBeVisible();
    expect(await serious(page), `${scheme} failed`).toEqual([]);
    await page.screenshot({ path: `test-results/scan-failed-${scheme}.png`, fullPage: true });
  });
}

test("history offers the right action for each scan state", async ({ page }) => {
  await stub(page, "completed");
  await page.goto("/#/history");
  await expect(page.getByRole("button", { name: "Cancel scan of example.org" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Retry scan of example.org" })).toHaveCount(2); // failed + cancelled
  expect(await serious(page), "history").toEqual([]);
});

test("a viewer does not see the audit log in the navigation", async ({ page }) => {
  await stub(page, "completed", viewer);
  await page.goto("/#/audit");
  await expect(page.getByText(/cannot view the audit log/)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Audit log" })).toHaveCount(0);
});

test("the audit log does not scroll the page sideways on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stub(page, "completed");
  await page.goto("/#/audit");
  await expect(page.getByRole("table")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("the scan history table scrolls inside its card on a phone, not the page", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stub(page, "completed");
  await page.goto("/#/history");
  await expect(page.getByRole("table")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test("real backend: a new owner sees their own sign-up in the audit log", async ({ page }) => {
  const email = uniqueEmail("audit");
  await register(page, email);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Audit log" }).click();
  const table = page.getByRole("table");
  await expect(table).toContainText("Account created");
  await expect(table).toContainText(email);
  expect(await serious(page), "real audit page").toEqual([]);
});
