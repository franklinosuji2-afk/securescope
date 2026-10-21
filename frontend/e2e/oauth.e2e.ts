import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** The sign-in and sign-up pages with the Google and GitHub buttons: accessible in both themes, no overflow. */
for (const scheme of ["dark", "light"] as const) {
  for (const [name, path] of [
    ["sign in", "/#/login"],
    ["sign in after a failed attempt", "/#/login?oauth_error=email_unverified"],
    ["sign up", "/#/register"],
  ] as const) {
    test(`${name} with provider buttons (${scheme})`, async ({ page }) => {
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
        if (url.endsWith("/auth/providers"))
          return json(200, { providers: ["google", "github"] });
        return json(200, {});
      });
      await page.goto(path);
      await expect(
        page.getByRole("link", { name: /with Google/ }),
      ).toBeVisible();
      await expect(
        page.getByRole("link", { name: /with GitHub/ }),
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
}
