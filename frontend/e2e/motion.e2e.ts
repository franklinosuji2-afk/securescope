import { expect, test } from "@playwright/test";

test.describe("motion", () => {
  test("buttons lift on hover and settle fully visible after the entrance", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      reducedMotion: "no-preference",
    });
    const page = await context.newPage();
    await page.goto("/#/");
    const cta = page.getByRole("link", { name: "Create free account" }).first();
    await expect(cta).toBeVisible();
    // The entrance animation finishes: nothing stays faded or shifted.
    await page.waitForTimeout(900);
    const settled = await page.evaluate(() => {
      const el = document.querySelector("#landing-main > section");
      return el ? getComputedStyle(el).opacity : "missing";
    });
    expect(settled).toBe("1");
    await cta.hover();
    await page.waitForTimeout(400);
    const transform = await cta.evaluate((e) => getComputedStyle(e).transform);
    expect(transform).not.toBe("none");
    await context.close();
  });

  test("with reduced motion nothing moves", async ({ page }) => {
    await page.goto("/#/");
    const cta = page.getByRole("link", { name: "Create free account" }).first();
    await cta.hover();
    await page.waitForTimeout(200);
    expect(await cta.evaluate((e) => getComputedStyle(e).transform)).toBe(
      "none",
    );
  });
});
