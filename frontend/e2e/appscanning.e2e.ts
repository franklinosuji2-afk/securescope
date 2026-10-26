import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { openMenu, register, uniqueEmail } from "./helpers";

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.passes.length, "axe evaluated no rules").toBeGreaterThan(10);
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({
      id: v.id,
      nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
}

const LOCK = JSON.stringify({
  lockfileVersion: 3,
  packages: {
    "": { name: "x" },
    "node_modules/lodash": { version: "4.17.20" },
  },
});

async function open(page: Page) {
  await register(page, uniqueEmail("appscan"));
  await openMenu(page);
  await page.getByRole("link", { name: "App Scanning" }).click();
  await expect(
    page.getByRole("heading", { name: "App Scanning", level: 1 }),
  ).toBeVisible();
}

test("a user can add a project, upload a lockfile and get an honest result", async ({
  page,
}) => {
  await open(page);
  await expect(page.getByText("No projects yet")).toBeVisible();
  await page.getByLabel("New project name").fill("web");
  await page.getByRole("button", { name: "Add project" }).click();
  await expect(page.getByLabel("Project")).toBeVisible();
  await page.getByLabel(/Dependency files/).setInputFiles({
    name: "package-lock.json",
    mimeType: "application/json",
    buffer: Buffer.from(LOCK),
  });
  await page.getByRole("button", { name: "Check dependencies" }).click();
  // No vulnerability source is configured on this backend: the answer must be an error, never "clean".
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: /Scanner error\. Nothing was checked/ }),
  ).toBeVisible();
  await expect(page.getByText(/No findings were detected/)).toHaveCount(0);
  await expect(page.getByText(/Runs this month: 0 of 5/)).toBeVisible();
});

test("a malformed file is refused with a clear message and is not counted", async ({
  page,
}) => {
  await open(page);
  await page.getByLabel("New project name").fill("web");
  await page.getByRole("button", { name: "Add project" }).click();
  await page.getByLabel(/Dependency files/).setInputFiles({
    name: "package-lock.json",
    mimeType: "application/json",
    buffer: Buffer.from("{not json"),
  });
  await page.getByRole("button", { name: "Check dependencies" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText(/Runs this month: 0 of 5/)).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`App Scanning has no serious accessibility violations (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await open(page);
    expect(await seriousViolations(page)).toEqual([]);
    await page.getByLabel("New project name").fill("web");
    await page.getByRole("button", { name: "Add project" }).click();
    await expect(page.getByLabel(/Dependency files/)).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });
}

test("works on a phone: no horizontal scroll and every control reachable by keyboard", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await open(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByLabel("New project name").focus();
  await page.keyboard.type("web");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel(/Dependency files/)).toBeVisible();
  await page.getByLabel(/Dependency files/).focus();
  await expect(page.getByLabel(/Dependency files/)).toBeFocused();
});
