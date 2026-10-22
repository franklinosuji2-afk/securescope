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

for (const scheme of ["dark", "light"] as const) {
  test(`the public sample report is accessible and fits every width (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/#/sample-report");
    await expect(
      page.getByRole("heading", { level: 1, name: "Sample security report" }),
    ).toBeVisible();
    await expect(page.getByRole("note")).toContainText("not a scan of a real");
    for (const width of [360, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      );
      expect(overflow, `no sideways scroll at ${width}px`).toBeLessThanOrEqual(
        0,
      );
    }
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}

test("the sample report shows real finding detail and links onward", async ({
  page,
}) => {
  await page.goto("/#/sample-report");
  const csp = page.getByRole("article", {
    name: "Content-Security-Policy header is missing",
  });
  await expect(csp).toContainText("Affected URL");
  await expect(csp).toContainText("How to verify the fix");
  await expect(
    page.getByRole("img", { name: /82 out of 100, grade B/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: "See pricing" }).click();
  await expect(page.getByRole("heading", { name: "Pricing" })).toBeInViewport();
});

test("the home page links to the sample report", async ({ page }) => {
  await page.goto("/#/");
  await page.getByRole("link", { name: "View sample report" }).click();
  await expect(page).toHaveURL(/#\/sample-report/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Sample security report" }),
  ).toBeVisible();
});

test("the plan comparison table is accessible and honest about plans", async ({
  page,
}) => {
  await page.goto("/#/");
  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  await expect(
    table.getByRole("columnheader", { name: "Agency" }),
  ).toBeVisible();
  await expect(
    table.getByRole("row", { name: /Scans per month 3 30 150/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Planned, not available yet" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "What SecureScope does not do" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});
