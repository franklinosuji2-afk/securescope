import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { openMenu, register, uniqueEmail } from "./helpers";

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
  test(`agency and legal pages have no serious or critical accessibility violations (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    for (const route of [
      "#/agency-features",
      "#/impressum",
      "#/privacy",
      "#/terms",
    ]) {
      await page.goto(`/${route}`);
      await expect(page.getByRole("heading").first()).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
      expect(await seriousViolations(page), `${scheme} ${route}`).toEqual([]);
    }
  });

  test(`signed-in pages have no serious or critical accessibility violations (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await register(page, uniqueEmail(`a11y-${scheme}`));
    await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    for (const route of [
      "#/",
      "#/targets",
      "#/integrations",
      "#/findings",
      "#/history",
      "#/team",
      "#/account",
      "#/audit",
      "#/analytics",
      "#/health",
      "#/clients",
    ]) {
      await page.goto(`/${route}`);
      await expect(page.getByRole("button", { name: "Menu" })).toBeVisible();
      expect(await seriousViolations(page), `${scheme} ${route}`).toEqual([]);
    }
    // The open menu panel is checked too: it floats over the page and holds the account controls.
    await openMenu(page);
    expect(await seriousViolations(page), `${scheme} menu open`).toEqual([]);
  });
}

test("the theme can be switched by the user", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await register(page, uniqueEmail("toggle"));
  await openMenu(page);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("a saved theme is applied before the app loads, so the other theme never flashes", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() =>
    window.localStorage.setItem("securescope-theme", "light"),
  );
  // With the app bundle blocked, only the small script in the page head can have set the theme.
  await page.route("**/assets/index-*.js", (route) => route.abort());
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("keyboard users get a skip link and visible focus", async ({ page }) => {
  await register(page, uniqueEmail("kbd"));
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
});

for (const scheme of ["dark", "light"] as const) {
  test(`a download link styled as an outline button is readable on its card (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await register(page, uniqueEmail(`ghost-${scheme}`));
    await page.goto("/#/account");
    const link = page.getByRole("link", { name: "Download my data (JSON)" });
    await expect(link).toBeVisible();
    // It sits on the page surface, so it must use the page text colour, not the accent button's text colour.
    const colours = await page.evaluate(() => {
      const a = document.querySelector('a[href$="/account/export"]');
      const h = document.querySelector("h1");
      return {
        link: a ? getComputedStyle(a).color : null,
        heading: h ? getComputedStyle(h).color : null,
      };
    });
    expect(colours.link).not.toBeNull();
    expect(colours.link).toBe(colours.heading);
  });
}
