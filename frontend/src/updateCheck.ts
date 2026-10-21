// Tells a tab that has been open for a while that a newer version of the site was released.
// Every release has built files with new names, so the name of the main script in the page is the version.

const BUNDLE = /\/assets\/index-[A-Za-z0-9_-]+\.js/;

/** The main script of a page's HTML, or null if there is none (for example an error page). */
export function bundleIn(html: string): string | null {
  return BUNDLE.exec(html)?.[0] ?? null;
}

/** The main script this tab is running. Null in development, where there is nothing to compare. */
export function runningBundle(doc: Document = document): string | null {
  for (const script of Array.from(doc.querySelectorAll("script[src]"))) {
    const found = BUNDLE.exec(script.getAttribute("src") ?? "");
    if (found) return found[0];
  }
  return null;
}

/** True only when the server clearly offers a different main script than the one running. Any doubt is false. */
export async function newVersionAvailable(
  fetcher: typeof fetch = fetch,
  doc: Document = document,
): Promise<boolean> {
  const running = runningBundle(doc);
  if (!running) return false;
  try {
    const response = await fetcher("/", { cache: "no-store" });
    if (!response.ok) return false;
    const offered = bundleIn(await response.text());
    return offered !== null && offered !== running;
  } catch {
    return false; // offline or blocked: say nothing
  }
}
