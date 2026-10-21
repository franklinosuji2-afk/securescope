import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const TOKEN = "T".repeat(43);

/** The invitation page and the Team invite form: accessible in both themes, no overflow. */
for (const scheme of ["dark", "light"] as const) {
  test(`accept-invitation page, signed out (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const json = (status: number, body: unknown) =>
        route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(body),
        });
      if (url.endsWith("/auth/me")) return json(401, { detail: "no" });
      if (url.includes("/invitations/preview"))
        return json(200, {
          organization_name:
            "A client workspace with a rather long name to check wrapping",
          email: "a-quite-long-client-address@example-company-name.org",
          role: "VIEWER",
        });
      return json(200, {});
    });
    await page.goto(`/#/accept-invite?token=${TOKEN}`);
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    for (const width of [360, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });

  test(`Team page with invite form and pending invitations (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const org = {
      id: "org1",
      name: "Alice Org",
      slug: "alice-org",
      role: "OWNER",
    };
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const json = (status: number, body: unknown) =>
        route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(body),
        });
      if (url.endsWith("/auth/me"))
        return json(200, {
          id: "u1",
          email: "alice@example.com",
          email_verified: true,
          organizations: [org],
        });
      if (url.endsWith("/organizations/org1/invitations"))
        return json(200, [
          {
            id: "i1",
            email: "a-quite-long-client-address@example-company-name.org",
            role: "VIEWER",
            invited_by_email: "alice@example.com",
            created_at: "2026-10-20T10:00:00Z",
            expires_at: "2026-10-27T10:00:00Z",
          },
        ]);
      if (url.endsWith("/organizations/org1"))
        return json(200, {
          ...org,
          members: [
            {
              user_id: "u1",
              email: "alice@example.com",
              role: "OWNER",
              joined_at: "2026-10-18T10:00:00Z",
            },
          ],
        });
      return json(200, {});
    });
    await page.goto("/#/team");
    await expect(
      page.getByRole("heading", { name: "Invite by email" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Pending invitations" }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    for (const width of [360, 768]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });
}
