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
    const cta = page.getByRole("link", { name: "Scan your website" }).first();
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

  test("the sample PDF cover reacts to the pointer and offers to open the file", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      reducedMotion: "no-preference",
    });
    const page = await context.newPage();
    await page.goto("/#/");
    const cover = page.getByRole("link", {
      name: "Open the sample PDF report",
    });
    await cover.evaluate((e) => e.scrollIntoView({ block: "center" }));
    const hint = cover.locator(".landing-pdf-hint");
    expect(await hint.evaluate((e) => getComputedStyle(e).opacity)).toBe("0");
    // The cover floats on its own, so Playwright never sees it "stable": hover without that wait.
    await cover.hover({ force: true });
    await page.waitForTimeout(500);
    expect(await hint.evaluate((e) => getComputedStyle(e).opacity)).toBe("1");
    expect(await cover.evaluate((e) => getComputedStyle(e).transform)).not.toBe(
      "none",
    );
    await context.close();
  });

  test("with reduced motion nothing moves", async ({ page }) => {
    await page.goto("/#/");
    const cta = page.getByRole("link", { name: "Scan your website" }).first();
    await cta.hover();
    await page.waitForTimeout(200);
    expect(await cta.evaluate((e) => getComputedStyle(e).transform)).toBe(
      "none",
    );
  });

  test("with reduced motion the sample PDF cover stays still", async ({
    page,
  }) => {
    await page.goto("/#/");
    const cover = page.getByRole("link", {
      name: "Open the sample PDF report",
    });
    await cover.scrollIntoViewIfNeeded();
    await cover.hover();
    await page.waitForTimeout(300);
    expect(await cover.evaluate((e) => getComputedStyle(e).transform)).toBe(
      "none",
    );
  });
});
