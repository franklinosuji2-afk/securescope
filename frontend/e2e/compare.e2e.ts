import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [{ id: "org1", name: "Org", slug: "org", role: "OWNER" }],
};
const summary = (id: string, at: string, score: number) => ({
  id,
  target_url: "https://a.example",
  host: "a.example",
  status: "completed",
  score,
  grade: "B",
  created_at: at,
  finished_at: at,
  counts: {},
});
const finding = (id: string, title: string, severity: string) => ({
  id,
  title,
  severity,
  category: "headers",
  description: "d",
  remediation: "r",
  confidence: "high",
  fingerprint: `fp-${id}`,
  status: "open",
});
const comparison = {
  host: "a.example",
  older: {
    id: "s1",
    scanned_at: "2026-10-01T10:00:00Z",
    status: "completed",
    score: 70,
    grade: "C",
  },
  newer: {
    id: "s2",
    scanned_at: "2026-10-08T10:00:00Z",
    status: "completed",
    score: 82,
    grade: "B",
  },
  score_change: 12,
  new_findings: [finding("N", "Cookie without Secure", "low")],
  resolved_findings: [finding("R", "CSP header is missing", "medium")],
  unchanged_findings: [finding("U", "No security.txt", "info")],
  note: "Findings are matched by their fingerprint. A finding that is missing from the newer scan was not detected there; that is not proof that it is fixed everywhere.",
};

async function stub(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.includes("/scans/s2/compare"))
      return route.fulfill({ json: comparison });
    if (url.includes("/scans/s2"))
      return route.fulfill({
        json: {
          ...summary("s2", "2026-10-08T10:00:00Z", 82),
          error: null,
          metadata: null,
          findings: [],
          score_note: "",
        },
      });
    if (url.includes("/scans?"))
      return route.fulfill({
        json: {
          items: [
            summary("s2", "2026-10-08T10:00:00Z", 82),
            summary("s1", "2026-10-01T10:00:00Z", 70),
          ],
          total: 2,
        },
      });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
}

for (const scheme of ["dark", "light"] as const) {
  test(`comparing two scans shows what changed and is accessible (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page);
    await page.goto("/#/compare?scan=s2");
    await expect(
      page.getByRole("heading", { level: 1, name: "Compare scans" }),
    ).toBeVisible();
    await expect(page.getByText("+12 points")).toBeVisible();
    await expect(page.getByText("Cookie without Secure")).toBeVisible();
    await expect(page.getByText("CSP header is missing")).toBeVisible();
    await expect(
      page.getByRole("region", { name: "No longer detected" }),
    ).toBeVisible();
    await expect(page.getByText("not proof")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(
      results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      ),
    ).toEqual([]);
  });
}

test("with no other scan it says so instead of showing an empty table", async ({
  page,
}) => {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.includes("/scans/s2"))
      return route.fulfill({
        json: {
          ...summary("s2", "2026-10-08T10:00:00Z", 82),
          error: null,
          metadata: null,
          findings: [],
          score_note: "",
        },
      });
    return route.fulfill({
      json: { items: [summary("s2", "2026-10-08T10:00:00Z", 82)], total: 1 },
    });
  });
  await page.goto("/#/compare?scan=s2");
  await expect(page.getByText("Nothing to compare yet")).toBeVisible();
});
