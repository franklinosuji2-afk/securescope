import { expect, type Page } from "@playwright/test";

export const PASSWORD = "correct-horse-battery-staple";

export function uniqueEmail(label: string): string {
  return `e2e-${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/** Registers through the real UI and waits until the signed-in shell is visible. */
export async function register(page: Page, email: string): Promise<void> {
  await page.goto("/#/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page
    .getByRole("button", { name: /create account|register|sign up/i })
    .click();
  await expect(page.getByRole("button", { name: "Menu" })).toBeVisible();
}

/** The navigation lives in the Menu panel at every width: open it if it is closed. */
export async function openMenu(page: Page): Promise<void> {
  const button = page.getByRole("button", { name: /^(Menu|Close menu)$/ });
  if ((await button.getAttribute("aria-expanded")) !== "true") {
    await button.click();
  }
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
}
