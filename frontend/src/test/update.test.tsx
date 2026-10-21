import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UpdateNotice from "../components/UpdateNotice";
import { bundleIn, newVersionAvailable, runningBundle } from "../updateCheck";

const OLD = "/assets/index-AAAA1111.js";
const NEW = "/assets/index-BBBB2222.js";

function pageWith(bundle: string): string {
  return `<!doctype html><html><body><div id="root"></div><script type="module" src="${bundle}"></script></body></html>`;
}

function runWith(bundle: string | null) {
  document.head.innerHTML = bundle
    ? `<script type="module" src="${bundle}"></script>`
    : "";
}

function fetcher(body: string, ok = true) {
  return vi.fn(async () => ({ ok, text: async () => body })) as never;
}

beforeEach(() => runWith(OLD));
afterEach(() => {
  document.head.innerHTML = "";
  vi.useRealTimers();
});

describe("version check", () => {
  it("finds the main script in a page and in the running tab", () => {
    expect(bundleIn(pageWith(NEW))).toBe(NEW);
    expect(bundleIn("<html>maintenance</html>")).toBeNull();
    expect(runningBundle()).toBe(OLD);
    runWith(null);
    expect(runningBundle()).toBeNull();
  });

  it("is true only when the server offers a different main script", async () => {
    expect(await newVersionAvailable(fetcher(pageWith(NEW)))).toBe(true);
    expect(await newVersionAvailable(fetcher(pageWith(OLD)))).toBe(false);
  });

  it("stays quiet when unsure: error page, failed request, offline, development", async () => {
    expect(await newVersionAvailable(fetcher("<html>oops</html>"))).toBe(false);
    expect(await newVersionAvailable(fetcher(pageWith(NEW), false))).toBe(
      false,
    );
    const offline = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as never;
    expect(await newVersionAvailable(offline)).toBe(false);
    runWith(null);
    expect(await newVersionAvailable(fetcher(pageWith(NEW)))).toBe(false);
  });
});

describe("the notice", () => {
  it("appears with a Reload button when a newer version exists, and does not reload by itself", async () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    vi.stubGlobal("fetch", fetcher(pageWith(NEW)));
    render(<UpdateNotice />);
    const button = await screen.findByRole("button", { name: "Reload" });
    expect(screen.getByRole("status")).toHaveTextContent(
      "A new version of SecureScope is available.",
    );
    expect(reload).not.toHaveBeenCalled();
    await userEvent.setup().click(button);
    expect(reload).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("shows nothing when the tab is current", async () => {
    vi.stubGlobal("fetch", fetcher(pageWith(OLD)));
    render(<UpdateNotice />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("status")).toBeNull();
    vi.unstubAllGlobals();
  });
});
