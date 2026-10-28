// Runs after `vite build`. The app uses hash routes, so the only real paths are the files below and the three
// links that emails contain. Cloudflare answers every other path with 404.html and a 404 status
// (not_found_handling "404-page" in wrangler.jsonc), so a mistyped address is no longer a "200 OK" page.
import { copyFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Paths the backend puts in emails (see main.tsx): each serves the app, which then moves to its hash route. */
export const EMAIL_LINK_PAGES = [
  "reset-password",
  "verify-email",
  "accept-invite",
];

/** Copies the built index.html to one file per email link, so those addresses still open the app. */
export function addEmailLinkPages(distDir) {
  const index = join(distDir, "index.html");
  if (!existsSync(index)) throw new Error(`No index.html in ${distDir}`);
  if (!existsSync(join(distDir, "404.html")))
    throw new Error(`No 404.html in ${distDir}: public/404.html is missing`);
  for (const name of EMAIL_LINK_PAGES)
    copyFileSync(index, join(distDir, `${name}.html`));
  return EMAIL_LINK_PAGES.map((name) => `${name}.html`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dist = fileURLToPath(new URL("../dist", import.meta.url));
  console.log(`Email link pages: ${addEmailLinkPages(dist).join(", ")}`);
}
