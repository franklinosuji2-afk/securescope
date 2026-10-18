import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { register, uniqueEmail } from "./helpers";

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    results.passes.length,
    "axe did not evaluate any rules",
  ).toBeGreaterThan(10);
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
}

test("public pages have no serious or critical accessibility violations", async ({
  page,
}) => {
  for (const route of ["#/login", "#/register", "#/forgot-password"]) {
    await page.goto(`/${route}`);
    await expect(page.getByRole("heading").first()).toBeVisible();
    expect(await seriousViolations(page), route).toEqual([]);
  }
});

for (const scheme of ["dark", "light"] as const) {
  test(`signed-in pages have no serious or critical accessibility violations (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await register(page, uniqueEmail(`a11y-${scheme}`));
    await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    for (const route of [
      "#/",
      "#/targets",
      "#/findings",
      "#/history",
      "#/team",
    ]) {
      await page.goto(`/${route}`);
      await expect(
        page.getByRole("navigation", { name: "Primary" }),
      ).toBeVisible();
      expect(await seriousViolations(page), `${scheme} ${route}`).toEqual([]);
    }
  });
}

test("the theme can be switched by the user", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await register(page, uniqueEmail("toggle"));
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("keyboard users get a skip link and visible focus", async ({ page }) => {
  await register(page, uniqueEmail("kbd"));
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
});
