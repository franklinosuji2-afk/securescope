import { execFileSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";

export const PASSWORD = "correct-horse-battery-staple";

export function uniqueEmail(label: string): string {
  return `e2e-${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/**
 * Stands in for opening the confirmation link from the email: the e2e backend has no mailbox, so the
 * address is marked confirmed straight in its throwaway SQLite database.
 */
function confirmEmailInDatabase(email: string): void {
  const file = (
    process.env.E2E_DATABASE_URL ?? "sqlite:////tmp/securescope-e2e.db"
  ).replace(/^sqlite:\/\/\//, "");
  execFileSync(process.env.E2E_PYTHON ?? "python", [
    "-c",
    "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute(\"update users set email_verified_at=datetime('now') where email=?\",(sys.argv[2].lower(),));c.commit()",
    file,
    email,
  ]);
}

/**
 * Registers through the real UI, confirms the address (the server requires it) and waits until the
 * signed-in shell is visible.
 */
export async function register(page: Page, email: string): Promise<void> {
  await page.goto("/#/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page
    .getByRole("button", { name: /create account|register|sign up/i })
    .click();
  await expect(
    page.getByRole("heading", { name: "Confirm your email address" }),
  ).toBeVisible();
  confirmEmailInDatabase(email);
  await page.getByRole("button", { name: "I have confirmed my email" }).click();
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
