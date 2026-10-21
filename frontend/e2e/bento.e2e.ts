import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** The Bento dashboard against a stubbed API: real-data cards, layout at each width, accessibility. */
const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "Example Org", slug: "example-org", role: "OWNER" },
  ],
};
const target = (hostname: string, status: string) => ({
  id: hostname,
  hostname,
  status,
  challenge_token: "a".repeat(32),
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: null,
  verification_method: null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: `_securescope-challenge.${hostname}`,
  dns_record_value: "securescope-verification=" + "a".repeat(32),
  http_file_url: `https://${hostname}/x`,
  http_file_content: "x",
});
const topFinding = {
  host: "a-very-long-hostname-for-wrapping.example.org",
  scan_id: "s2",
  finding_id: "SS-HDR-HSTS-001",
  title: "Strict-Transport-Security header is missing",
  severity: "high",
  confidence: "high",
  remediation: "Send the header.",
};
const overview = {
  sites: [
    {
      host: topFinding.host,
      latest_scan_id: "s2",
      score: 62,
      grade: "C",
      scanned_at: "2026-10-18T12:00:00Z",
      previous_score: 55,
      score_change: 7,
      open_counts: { high: 1 },
      open_total: 1,
      top_finding: topFinding,
      history: [
        { scan_id: "s1", score: 55, scanned_at: "2026-10-17T12:00:00Z" },
        { scan_id: "s2", score: 62, scanned_at: "2026-10-18T12:00:00Z" },
      ],
    },
  ],
  fix_first: topFinding,
  other_open: 0,
};
const scanRow = (id: string, status: string) => ({
  id,
  target_url: `https://${id === "s1" ? "other.example.org" : topFinding.host}/`,
  host: id === "s1" ? "other.example.org" : topFinding.host,
  status,
  score: status === "completed" ? 62 : null,
  grade: status === "completed" ? "C" : null,
  created_at: id === "s2" ? "2026-10-18T12:00:00Z" : "2026-10-17T12:00:00Z",
  finished_at: "2026-10-18T12:00:01Z",
  counts: status === "completed" ? { high: 1 } : {},
});

async function stub(page: Page, scansFail = false) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/scans?") && scansFail)
      return route.fulfill({ status: 500, json: { detail: "scan list down" } });
    let body: unknown = { items: [], total: 0 };
    if (url.endsWith("/auth/me")) body = user;
    else if (url.includes("/targets"))
      body = {
        items: [
          target(topFinding.host, "verified"),
          target("new.example.org", "pending"),
        ],
      };
    else if (url.includes("/overview")) body = overview;
    else if (url.includes("/scans/s2"))
      body = {
        ...scanRow("s2", "completed"),
        error: null,
        metadata: null,
        score_note: "Heuristic score.",
        findings: [
          {
            ...topFinding,
            id: topFinding.finding_id,
            severity: "high",
            category: "Security headers",
            description: "d",
            evidence: "e",
            fingerprint: "1".repeat(32),
            status: "open",
            status_note: null,
            first_seen_at: "2026-10-18T10:00:00Z",
            last_seen_at: "2026-10-18T12:00:00Z",
          },
        ],
      };
    else if (url.includes("/scans?"))
      body = {
        items: [scanRow("s2", "completed"), scanRow("s1", "failed")],
        total: 2,
      };
    await route.fulfill({ json: body });
  });
}

for (const width of [360, 390, 768, 1024, 1440]) {
  test(`bento fits without sideways scrolling at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await stub(page);
    await page.goto("/#/");
    await expect(
      page.getByRole("heading", { name: "Security posture" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    // Every card stays inside the page; none is clipped on the right.
    const clipped = await page.evaluate(
      () =>
        [...document.querySelectorAll(".bento > *")].filter(
          (el) => el.getBoundingClientRect().right > window.innerWidth + 1,
        ).length,
    );
    expect(clipped).toBe(0);
    await page.screenshot({
      path: `test-results/bento-${width}.png`,
      fullPage: true,
    });
  });
}

for (const scheme of ["dark", "light"] as const) {
  test(`bento shows real data and passes accessibility checks (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stub(page);
    await page.goto("/#/");
    const bento = page.locator(".bento");
    await expect(
      bento.getByRole("img", {
        name: /Heuristic score 62 out of 100, grade C/,
      }),
    ).toBeVisible();
    await expect(bento.getByTestId("bento-chip")).toBeVisible();
    await expect(
      bento.getByRole("link", { name: /Strict-Transport-Security/ }).first(),
    ).toBeVisible();
    await expect(
      bento.getByRole("link", { name: "Verify new.example.org" }),
    ).toBeVisible();
    await expect(
      bento.getByRole("link", { name: /Investigate the failed scan/ }),
    ).toBeVisible();
    await expect(
      bento.getByRole("button", { name: /Download PDF report/ }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const bad = results.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({
        id: v.id,
        nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
      }));
    expect(bad, `${scheme} bento`).toEqual([]);
  });
}

test("a failing scan list shows an error and keeps the other cards honest", async ({
  page,
}) => {
  await stub(page, true);
  await page.goto("/#/");
  const bento = page.locator(".bento");
  await expect(bento.getByRole("alert")).toContainText("scan list down");
  await expect(bento.getByText("No scans yet.")).toHaveCount(0);
  await expect(
    bento.getByRole("img", { name: /Heuristic score 62/ }),
  ).toBeVisible();
});

test("reduced motion shows the finished gauge with no transition", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await stub(page);
  await page.goto("/#/");
  const arc = page.locator(".gauge-arc");
  await expect(arc).toBeVisible();
  const seconds = await arc.evaluate((e) =>
    parseFloat(getComputedStyle(e).transitionDuration),
  );
  expect(seconds).toBeLessThan(0.001);
});

test("the gauge ring fills to the real score", async ({ page }) => {
  await stub(page);
  await page.goto("/#/");
  const arc = page.locator(".gauge-arc");
  const circumference = 2 * Math.PI * 52;
  await expect
    .poll(async () =>
      arc.evaluate((e) =>
        parseFloat(e.getAttribute("stroke-dashoffset") ?? "0"),
      ),
    )
    .toBeCloseTo(circumference * (1 - 0.62), 0);
});

test("bento links work by keyboard and show a focus ring", async ({ page }) => {
  await stub(page);
  await page.goto("/#/");
  const row = page
    .locator(".bento-issues")
    .getByRole("link", { name: /Strict-Transport-Security/ });
  await row.focus();
  expect(await row.evaluate((e) => getComputedStyle(e).outlineStyle)).not.toBe(
    "none",
  );
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Strict-Transport-Security header is missing",
    }),
  ).toBeVisible();
});
