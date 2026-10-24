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
      await expect
        .poll(
          () =>
            page.evaluate(
              () =>
                document.documentElement.scrollWidth -
                document.documentElement.clientWidth,
            ),
          { message: `horizontal overflow at ${width}px` },
        )
        .toBeLessThanOrEqual(0);
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
      await expect
        .poll(
          () =>
            page.evaluate(
              () =>
                document.documentElement.scrollWidth -
                document.documentElement.clientWidth,
            ),
          { message: `no sideways scroll at ${width}px` },
        )
        .toBeLessThanOrEqual(0);
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

test("the home page has a theme toggle that switches and remembers the theme", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/#/");
  const html = page.locator("html");
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(html).toHaveAttribute("data-theme", "dark");
});

test("the header never wraps or overflows between phone and desktop widths", async ({
  page,
}) => {
  await page.goto("/#/");
  for (const width of [320, 861, 900, 1024, 1241, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(0);
    if (width >= 1241) {
      const heights = await page
        .locator(".landing-links > *")
        .evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
      // Every link stays on one line.
      for (const h of heights) expect(h).toBeLessThan(48);
    }
  }
});

test("the sample report card links to the full sample report", async ({
  page,
}) => {
  await page.goto("/#/");
  await page.getByRole("link", { name: /Open the full sample report/ }).click();
  await expect(page).toHaveURL(/#\/sample-report/);
});

test("the numbers in The Answer keep clear space around their labels", async ({
  page,
}) => {
  await page.goto("/#/");
  const gap = await page
    .locator(".landing-numbers > div")
    .first()
    .evaluate((el) => {
      const dt = el.querySelector("dt")!.getBoundingClientRect();
      const dd = el.querySelector("dd")!.getBoundingClientRect();
      const note = document
        .querySelector(".landing-fineprint")!
        .getBoundingClientRect();
      return { between: dd.top - dt.bottom, below: note.top - dd.bottom };
    });
  expect(gap.between).toBeGreaterThanOrEqual(12);
  expect(gap.below).toBeGreaterThanOrEqual(24);
});

test("the public pages never overflow between phone and desktop widths", async ({
  page,
}) => {
  for (const route of ["/#/sample-report", "/#/agency-features"]) {
    await page.goto(route);
    for (const width of [320, 861, 900, 1024, 1101, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expect
        .poll(
          () =>
            page.evaluate(
              () =>
                document.documentElement.scrollWidth -
                document.documentElement.clientWidth,
            ),
          { message: `${route} at ${width}px` },
        )
        .toBeLessThanOrEqual(0);
    }
  }
});

test.describe("floating cards", () => {
  test.use({ reducedMotion: "no-preference" });
  const cases: [string, string[]][] = [
    [
      "",
      [
        ".landing-sample",
        ".landing-card",
        ".landing-numbers > div",
        ".landing-final",
      ],
    ],
    [
      "sample-report",
      [
        ".sample-notice",
        ".sample-toc",
        ".sample-score",
        ".sample-finding",
        ".sample-cta",
      ],
    ],
    ["agency-features", [".landing-card", ".agency-availability"]],
  ];
  for (const [route, selectors] of cases) {
    test(`cards on /${route || "home"} lift under the pointer`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`/#/${route}`);
      for (const selector of selectors) {
        const el = page.locator(selector).first();
        await el.evaluate((node) => node.scrollIntoView({ block: "center" }));
        await page.waitForTimeout(100);
        const box = await el.boundingBox();
        expect(box, selector).not.toBeNull();
        await page.mouse.move(
          box!.x + box!.width / 2,
          box!.y + Math.min(box!.height / 2, 40),
        );
        await expect
          .poll(
            () =>
              el.evaluate((node) => {
                const cs = getComputedStyle(node);
                return cs.transform !== "none";
              }),
            { message: `${selector} should lift on hover` },
          )
          .toBe(true);
        await page.mouse.move(0, 0);
      }
    });
  }

  test("the header theme button matches the buttons beside it", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/#/sample-report");
    const toggle = page.getByRole("button", { name: /Switch to/ });
    const signIn = page.getByRole("link", { name: "Sign in" }).first();
    const t = await toggle.boundingBox();
    const s = await signIn.boundingBox();
    expect(Math.abs(t!.height - s!.height)).toBeLessThanOrEqual(3);
    await toggle.click();
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      /light|dark/,
    );
    const before = await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    );
    await toggle.click();
    await expect
      .poll(() =>
        page.evaluate(() => getComputedStyle(document.body).backgroundColor),
      )
      .not.toBe(before);
  });
});

test("the home page offers the sample report as a PDF that really downloads", async ({
  page,
}) => {
  await page.goto("/#/");
  const links = page.getByRole("link", { name: /Download the sample PDF/ });
  await expect(links).toHaveCount(2); // the hero card and the sample section
  for (const link of await links.all())
    await expect(link).toHaveAttribute("href", "/sample-report.pdf");
  const response = await page.request.get("/sample-report.pdf");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  const body = await response.body();
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  expect(body.length).toBeGreaterThan(10_000);
});

for (const scheme of ["dark", "light"] as const) {
  test(`the agency page is accessible, balanced and fits every width (${scheme} theme)`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/#/agency-features");
    await expect(
      page.getByRole("heading", { level: 1, name: /Security reports/ }),
    ).toBeVisible();
    // Two groups of four feature cards, and an availability note.
    await expect(
      page.getByRole("heading", { level: 2, name: "Work for your clients" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: "Share and automate" }),
    ).toBeVisible();
    await expect(page.locator(".agency-grid .landing-card")).toHaveCount(8);
    await expect(
      page.getByRole("heading", { level: 2, name: "Availability" }),
    ).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(
      results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => v.id),
    ).toEqual([]);
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await expect
        .poll(() =>
          page.evaluate(
            () =>
              document.documentElement.scrollWidth -
              document.documentElement.clientWidth,
          ),
        )
        .toBeLessThanOrEqual(0);
    }
  });
}
