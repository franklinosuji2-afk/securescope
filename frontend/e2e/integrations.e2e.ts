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
const badgeUrl = "/favicon.svg";

async function stub(page: Page, available: boolean) {
  const created: unknown[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.endsWith("/targets"))
      return route.fulfill({ json: { items: [target] } });
    if (url.endsWith("/api-tokens") && method === "POST") {
      created.push(route.request().postDataJSON());
      return route.fulfill({
        status: 201,
        json: {
          id: "k1",
          name: "GitHub Actions",
          prefix: "ssk_ab12",
          created_at: "2026-10-22T10:00:00Z",
          last_used_at: null,
          created_by_email: "owner@example.org",
          token: "ssk_" + "b".repeat(43),
        },
      });
    }
    if (url.endsWith("/api-tokens"))
      return route.fulfill({ json: { available, limit: 5, items: [] } });
    if (url.endsWith("/badges/t1") && method === "PUT")
      return route.fulfill({
        json: {
          target_id: "t1",
          hostname: "acme.example",
          enabled: true,
          url: badgeUrl,
        },
      });
    if (url.endsWith("/badges"))
      return route.fulfill({
        json: {
          items: [
            {
              target_id: "t1",
              hostname: "acme.example",
              enabled: false,
              url: null,
            },
          ],
        },
      });
    if (url.endsWith("/webhooks"))
      return route.fulfill({
        json: { available: false, configured: true, limit: 3, items: [] },
      });
    if (url.endsWith("/schedules"))
      return route.fulfill({ json: { available: false, items: [] } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  return created;
}

for (const scheme of ["dark", "light"] as const) {
  test(`a CI token is shown once and a badge can be switched on (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const created = await stub(page, true);
    await page.goto("/#/integrations");
    await expect(
      page.getByRole("heading", { level: 2, name: "API tokens for CI" }),
    ).toBeVisible();
    await page.getByLabel("Token name").fill("GitHub Actions");
    await page.getByRole("button", { name: "Create token" }).click();
    await expect(page.getByText(/^ssk_b+$/)).toBeVisible();
    expect(created).toEqual([{ name: "GitHub Actions" }]);
    await page.getByRole("button", { name: "I have saved it" }).click();
    await expect(page.getByText(/^ssk_b+$/)).toHaveCount(0);

    await expect(page.getByText("The badge is off.")).toBeVisible();
    await page.getByRole("button", { name: "Switch badge on" }).click();
    await expect(page.getByLabel("Markdown")).toHaveValue(
      `[![SecureScope](${badgeUrl})](https://getsecurescope.com)`,
    );

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

test("a plan without CI access says so", async ({ page }) => {
  await stub(page, false);
  await page.goto("/#/integrations");
  await expect(page.getByText(/does not include API tokens/)).toBeVisible();
  await expect(page.getByLabel("Token name")).toHaveCount(0);
});
