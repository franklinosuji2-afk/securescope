import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Stubbed API: checks how the Overview reads in each state, and its accessibility, in both themes. */
const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" },
  ],
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

function summary(
  id: string,
  host: string,
  created: string,
  score: number,
  grade: string,
  counts: object,
) {
  return {
    id,
    target_url: `https://${host}/`,
    host,
    status: "completed",
    score,
    grade,
    created_at: created,
    finished_at: created,
    counts,
  };
}

const finding = (
  id: string,
  title: string,
  severity: string,
  n: string,
  status = "open",
) => ({
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

const topFinding = {
  host: "example.org",
  scan_id: "s2",
  finding_id: "SS-HDR-HSTS-001",
  title: "Strict-Transport-Security header is missing",
  severity: "high",
  confidence: "high",
  remediation:
    "Send 'Strict-Transport-Security: max-age=31536000; includeSubDomains'.",
};

const overview = {
  sites: [
    {
      host: "example.org",
      latest_scan_id: "s2",
      score: 84,
      grade: "B",
      scanned_at: "2026-10-18T12:00:00Z",
      previous_score: 76,
      score_change: 8,
      open_counts: { high: 1, low: 1 },
      open_total: 2,
      top_finding: topFinding,
      history: [
        { scan_id: "s0", score: 60, scanned_at: "2026-10-16T12:00:00Z" },
        { scan_id: "s1", score: 76, scanned_at: "2026-10-18T10:00:00Z" },
        { scan_id: "s2", score: 84, scanned_at: "2026-10-18T12:00:00Z" },
      ],
    },
  ],
  fix_first: topFinding,
  other_open: 1,
};

const findingsScan = {
  ...summary("s2", "example.org", "2026-10-18T12:00:00Z", 84, "B", {
    high: 1,
    low: 1,
  }),
  error: null,
  metadata: null,
  score_note: "Heuristic score.",
  findings: [
    finding(
      "SS-HDR-HSTS-001",
      "Strict-Transport-Security header is missing",
      "high",
      "1",
    ),
    finding(
      "SS-COOKIE-SAMESITE-001",
      "Cookies set without an explicit SameSite attribute",
      "low",
      "2",
    ),
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
          state === "new"
            ? []
            : state === "verified"
              ? [target("example.org", "verified")]
              : [
                  target("example.org", "verified"),
                  target("staging.example.org", "pending"),
                ],
      };
    } else if (url.includes("/overview"))
      body =
        state === "scanned"
          ? overview
          : { sites: [], fix_first: null, other_open: 0 };
    else if (url.includes("/scans/s2")) body = findingsScan;
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
  test(`new account: guided setup is clear and accessible (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "new");
    await page.goto("/#/");
    await expect(
      page.getByRole("heading", { name: "Get your first result" }),
    ).toBeVisible();
    await expect(page.locator("li[aria-current=step]")).toContainText(
      "Add the site you want to check",
    );
    expect(await serious(page), `${scheme} guide`).toEqual([]);
    await page.screenshot({
      path: `test-results/overview-new-${scheme}.png`,
      fullPage: true,
    });
  });

  test(`scanned account: fix-first and site cards are accurate and accessible (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page, "scanned");
    await page.goto("/#/");
    await expect(
      page.getByRole("heading", { name: "Fix this first" }),
    ).toBeVisible();
    await expect(
      page.getByText("Strict-Transport-Security header is missing").first(),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Get your first result" }),
    ).toHaveCount(0);
    const card = page.getByRole("listitem", { name: "example.org" });
    await expect(card).toContainText("84");
    await expect(card).toContainText("Up 8 since the previous scan");
    await expect(card).toContainText("2 open");
    await expect(
      card.getByRole("img", { name: /Score history over 3 scans: 60, 76, 84/ }),
    ).toBeVisible();
    expect(await serious(page), `${scheme} posture`).toEqual([]);
    await page.screenshot({
      path: `test-results/overview-scanned-${scheme}.png`,
      fullPage: true,
    });
  });
}

test("verified sites fill the scan form, and the fix link opens the finding", async ({
  page,
}) => {
  await stub(page, "scanned");
  await page.goto("/#/");
  await page.getByRole("button", { name: "example.org", exact: true }).click();
  await expect(page.getByLabel("Target URL")).toHaveValue(
    "https://example.org/",
  );
  await page.getByRole("link", { name: "See the evidence and fix" }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Strict-Transport-Security header is missing",
    }),
  ).toBeVisible();
});

test("overview does not scroll sideways on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stub(page, "scanned");
  await page.goto("/#/");
  await expect(
    page.getByRole("heading", { name: "Fix this first" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("on a phone the navigation is a menu that works by keyboard and passes accessibility checks", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await stub(page, "scanned");
  await page.goto("/#/");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  await menu.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  expect(await serious(page), "menu open").toEqual([]);
  await page.screenshot({ path: "test-results/overview-mobile-menu.png" });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  await expect(menu).toBeFocused();
  await menu.click();
  await page.getByRole("link", { name: "Targets" }).click();
  await expect(
    page.getByRole("heading", { name: "Targets", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("on a desktop the navigation is the same floating Menu, closed until opened", async ({
  page,
}) => {
  await stub(page, "scanned");
  await page.goto("/#/");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  await menu.click();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  // The account controls sit in the same panel.
  await expect(
    page.getByRole("button", { name: /Switch to (light|dark) theme/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  // A press outside closes it.
  await page.mouse.click(5, 400);
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
});
