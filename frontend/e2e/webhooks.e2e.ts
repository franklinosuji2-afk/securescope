import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "u1",
  email: "owner@example.org",
  email_verified: true,
  organizations: [{ id: "org1", name: "Org", slug: "org", role: "OWNER" }],
};
const target = {
  id: "t1",
  hostname: "acme.example",
  status: "verified",
  challenge_token: "x".repeat(32),
  challenge_expires_at: "2026-12-01T10:00:00Z",
  verified_at: "2026-10-01T10:00:00Z",
  verification_expires_at: "2027-10-01T10:00:00Z",
  verification_method: "dns_txt",
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-01T10:00:00Z",
  dns_record_name: "_securescope.acme.example",
  dns_record_value: "securescope-verify=x",
  http_file_url: "",
  http_file_content: "",
};
const hook = {
  id: "w1",
  address: "https://hooks.example.com/…",
  enabled: true,
  last_attempt_at: null,
  last_status: null,
  consecutive_failures: 0,
  created_at: "2026-10-22T10:00:00Z",
};

async function stub(
  page: Page,
  state: { available: boolean; configured: boolean },
) {
  const created: unknown[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.endsWith("/targets"))
      return route.fulfill({ json: { items: [target] } });
    if (url.endsWith("/webhooks") && method === "POST") {
      created.push(route.request().postDataJSON());
      return route.fulfill({
        status: 201,
        json: { ...hook, signing_secret: "whsec_" + "a".repeat(64) },
      });
    }
    if (url.endsWith("/webhooks"))
      return route.fulfill({
        json: { ...state, limit: 3, items: [] },
      });
    if (url.endsWith("/schedules"))
      return route.fulfill({ json: { available: false, items: [] } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  return created;
}

for (const scheme of ["dark", "light"] as const) {
  test(`a webhook address can be added, its secret is shown once, and the page is accessible (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const created = await stub(page, { available: true, configured: true });
    await page.goto("/#/targets");
    await expect(
      page.getByRole("heading", { level: 2, name: "Webhook alerts" }),
    ).toBeVisible();
    await page
      .getByLabel("Webhook address")
      .fill("https://hooks.example.com/secret-token");
    await page.getByRole("button", { name: "Add webhook address" }).click();
    await expect(page.getByText(/^whsec_a+$/)).toBeVisible();
    await expect(page.getByText("https://hooks.example.com/…")).toBeVisible();
    expect(created).toEqual([
      { url: "https://hooks.example.com/secret-token", kind: "webhook" },
    ]);
    await page.getByRole("button", { name: "I have saved it" }).click();
    await expect(page.getByText(/^whsec_/)).toHaveCount(0);
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

test("a server without a signing key says so", async ({ page }) => {
  await stub(page, { available: true, configured: false });
  await page.goto("/#/targets");
  await expect(
    page.getByText("Webhook alerts are not switched on for this server yet."),
  ).toBeVisible();
  await expect(page.getByLabel("Webhook address")).toHaveCount(0);
});
