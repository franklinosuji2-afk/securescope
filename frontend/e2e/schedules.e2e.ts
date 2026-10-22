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
const site = (frequency: string) => ({
  target_id: "t1",
  hostname: "acme.example",
  frequency,
  url: "https://acme.example/",
  notify: true,
  next_run_at: frequency === "off" ? null : "2026-10-23T10:00:00Z",
  last_run_at: null,
  last_scan_id: null,
  last_outcome: null,
});

async function stub(page: Page, available: boolean) {
  const saved: unknown[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/auth/me")) return route.fulfill({ json: user });
    if (url.endsWith("/targets"))
      return route.fulfill({ json: { items: [target] } });
    if (url.includes("/schedules/t1")) {
      const body = route.request().postDataJSON() as { frequency: string };
      saved.push(body);
      return route.fulfill({ json: site(body.frequency) });
    }
    if (url.endsWith("/schedules"))
      return route.fulfill({ json: { available, items: [site("off")] } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  return saved;
}

for (const scheme of ["dark", "light"] as const) {
  test(`a site can be scheduled from Targets and the page is accessible (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const saved = await stub(page, true);
    await page.goto("/#/targets");
    await expect(
      page.getByRole("heading", { level: 2, name: "Scheduled scans" }),
    ).toBeVisible();
    await expect(page.getByText("Not scheduled.")).toBeVisible();
    await page.getByLabel("How often").selectOption("weekly");
    await expect(page.getByText(/Next run after/)).toBeVisible();
    expect(saved).toEqual([{ frequency: "weekly", notify: true }]);
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

test("a plan without scheduled scans says so plainly", async ({ page }) => {
  await stub(page, false);
  await page.goto("/#/targets");
  await expect(
    page.getByText("Your plan does not include them."),
  ).toBeVisible();
  await expect(page.getByLabel("How often")).toHaveCount(0);
});
