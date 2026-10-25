import { expect, test } from "@playwright/test";
import { register, uniqueEmail } from "./helpers";

test.describe("targets and scan gating (real backend)", () => {
  test("a new user cannot scan an unverified domain and sees how to verify one", async ({
    page,
  }) => {
    await register(page, uniqueEmail("targets"));

    // Overview: honest empty state, nothing fabricated.
    await expect(
      page.getByRole("heading", { name: "Get your first result" }),
    ).toBeVisible();
    await expect(page.getByText(/No scan yet/)).toBeVisible();

    // Scanning an unverified domain is refused by the server and the UI explains why.
    await page.getByLabel("Target URL").fill("https://example.com");
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Start scan" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "has not been verified",
    );
    await page.getByRole("link", { name: "Go to Targets" }).click();
    await expect(
      page.getByRole("heading", { name: "Targets", exact: true }),
    ).toBeVisible();

    // Invalid targets are rejected by the server.
    await page.getByLabel("Domain name").fill("10.0.0.1");
    await page.getByRole("button", { name: "Add domain" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "IP addresses cannot be verified",
    );

    // A valid domain is registered with exact, copyable instructions.
    await page.getByLabel("Domain name").fill("Example.com");
    await page.getByRole("button", { name: "Add domain" }).click();
    const card = page.getByRole("listitem", { name: "example.com" });
    await expect(card.getByText("Not verified")).toBeVisible();
    await expect(
      card.getByText("_securescope-challenge.example.com"),
    ).toBeVisible();
    await expect(
      card.getByText("/.well-known/securescope-verification.txt"),
    ).toBeVisible();

    // Verification is a real server-side check. Nothing is published, so it must fail honestly.
    await card.getByRole("button", { name: "Verify DNS record" }).click();
    await expect(card.getByRole("alert")).toBeVisible();
    await expect(card.getByText("Not verified")).toBeVisible();
    await expect(card.getByText("Verified", { exact: true })).toHaveCount(0);

    // Removal needs an explicit confirmation.
    await card.getByRole("button", { name: "Remove", exact: true }).click();
    await card
      .getByRole("button", { name: /Confirm removal of example.com/ })
      .click();
    await expect(page.getByText("No targets yet")).toBeVisible();
  });

  test("another account never sees the first account's targets", async ({
    browser,
  }) => {
    const first = await browser.newPage();
    await register(first, uniqueEmail("owner"));
    await first.goto("/#/targets");
    await first.getByLabel("Domain name").fill("private-to-first.example.org");
    await first.getByRole("button", { name: "Add domain" }).click();
    await expect(
      first.getByRole("heading", { name: "private-to-first.example.org" }),
    ).toBeVisible();

    const second = await (await browser.newContext()).newPage();
    await register(second, uniqueEmail("other"));
    await second.goto("/#/targets");
    await expect(second.getByText("No targets yet")).toBeVisible();
    await expect(second.getByText("private-to-first.example.org")).toHaveCount(
      0,
    );
  });
});
