import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const scheme of ["dark", "light"] as const) {
  test(`the public home page is accessible and fits every width (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/#/");
    await expect(
      page.getByRole("heading", { level: 1, name: /Find the gaps/ }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => n.target.join(" ")),
        })),
    ).toEqual([]);
    for (const width of [320, 360, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(
        0,
      );
    }
  });
}

test("the home page leads to registration and sign-in, and scrolls to its sections", async ({
  page,
}) => {
  await page.goto("/#/");
  await page
    .getByRole("navigation", { name: "Site" })
    .getByRole("button", { name: "Pricing" })
    .click();
  await expect(page.getByRole("heading", { name: "Pricing" })).toBeInViewport();
  await page.getByRole("link", { name: "Create free account" }).first().click();
  await expect(page).toHaveURL(/#\/register/);
  await page.goto("/#/");
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/#\/login/);
});

test("on a phone the section links open from a menu that closes with Escape", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(
    page
      .getByRole("navigation", { name: "Site" })
      .getByRole("button", { name: "Pricing" }),
  ).toBeHidden();
  await menu.click();
  await expect(
    page.getByRole("button", { name: "Close menu" }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Menu" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await page.getByRole("button", { name: "Menu" }).click();
  await page
    .getByRole("navigation", { name: "Site" })
    .getByRole("button", { name: "Pricing" })
    .click();
  await expect(page.getByRole("heading", { name: "Pricing" })).toBeInViewport();
  await expect(page.getByRole("button", { name: "Menu" })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
});
