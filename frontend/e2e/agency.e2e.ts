import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "Agency Org", slug: "agency-org", role: "OWNER" },
  ],
};
const none = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
const dashboard = {
  total_clients: 1,
  total_sites: 2,
  clients: [
    {
      client_id: "c1",
      name: "Acme Ltd",
      sites: [
        {
          target_id: "t1",
          hostname: "acme.example",
          verified: true,
          last_scan_id: "s1",
          last_scan_at: "2026-10-18T10:00:00Z",
          score: 82,
          grade: "B",
          open_findings: { ...none, medium: 1, low: 2 },
        },
      ],
      open_findings: { ...none, medium: 1, low: 2 },
      worst_grade: "B",
      last_scan_at: "2026-10-18T10:00:00Z",
    },
    {
      client_id: null,
      name: "Not assigned to a client",
      sites: [
        {
          target_id: "t2",
          hostname: "loose.example",
          verified: true,
          last_scan_id: null,
          last_scan_at: null,
          score: null,
          grade: null,
          open_findings: none,
        },
      ],
      open_findings: none,
      worst_grade: null,
      last_scan_at: null,
    },
  ],
};
const clients = [
  {
    id: "c1",
    name: "Acme Ltd",
    contact_email: "it@acme.example",
    notes: "Prefers Monday reports",
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    site_count: 1,
  },
];

async function stubApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { items: [], total: 0 };
    if (url.endsWith("/auth/me")) body = user;
    else if (url.endsWith("/agency/dashboard")) body = dashboard;
    else if (url.endsWith("/agency/clients")) body = { items: clients };
    else if (url.endsWith("/agency/branding"))
      body = { agency_name: "Nordlicht" };
    await route.fulfill({ json: body });
  });
}

for (const scheme of ["dark", "light"] as const) {
  test(`the clients page shows real stored numbers and is accessible (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await stubApi(page);
    await page.goto("/#/clients");
    await expect(
      page.getByRole("heading", { level: 1, name: "Clients" }),
    ).toBeVisible();
    await expect(page.getByText("82 (B)")).toBeVisible();
    await expect(page.getByText("Not scanned")).toBeVisible();
    await expect(page.getByText("Prefers Monday reports")).toBeVisible();
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

test("a workspace without client features does not show the Clients page", async ({
  page,
}) => {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.includes("/agency/"))
      return route.fulfill({
        status: 403,
        json: { detail: "Client workspaces are part of the Agency plan." },
      });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/#/");
  await expect(page.getByRole("button", { name: "Menu" })).toBeVisible();
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("link", { name: "Targets" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Clients" })).toHaveCount(0);
});

test("a shared report link opens without signing in and says plainly when it is no good", async ({
  page,
}) => {
  const token = "A".repeat(43);
  await page.route("**/api/v1/shared/**", async (route) => {
    if (route.request().url().includes(token))
      return route.fulfill({
        json: {
          host: "acme.example",
          scanned_at: "2026-10-18T10:00:00Z",
          score: 82,
          grade: "B",
          prepared_by: "Nordlicht",
          expires_at: "2026-11-18T10:00:00Z",
          download_path: `/api/v1/shared/${token}/report.pdf`,
        },
      });
    return route.fulfill({ status: 404, json: { detail: "Not found." } });
  });
  await page.goto(`/#/shared?token=${token}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "acme.example" }),
  ).toBeVisible();
  await expect(page.getByText("Nordlicht")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open the PDF report" }),
  ).toHaveAttribute("href", `/api/v1/shared/${token}/report.pdf`);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(results.violations).toEqual([]);

  await page.goto(`/#/shared?token=${"B".repeat(43)}`);
  await expect(page.getByRole("alert")).toContainText("not valid");
  await page.goto("/#/shared");
  await expect(page.getByRole("alert")).toContainText("not valid");
});

for (const scheme of ["dark", "light"] as const) {
  test(`the agency explainer is public, honest and accessible (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/#/agency-features");
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Security reports your clients can read",
      }),
    ).toBeVisible();
    await expect(page.getByText("cannot buy Agency today")).toBeVisible();
    for (const width of [360, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expect
        .poll(() =>
          page.evaluate(
            () =>
              document.documentElement.scrollWidth -
              document.documentElement.clientWidth,
          ),
        )
        .toBeLessThanOrEqual(0);
    }
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}

test("the home page leads to the agency explainer", async ({ page }) => {
  await page.goto("/#/");
  await page.getByRole("link", { name: "Explore Agency features" }).click();
  await expect(page).toHaveURL(/#\/agency-features/);
});
