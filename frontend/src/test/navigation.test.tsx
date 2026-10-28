import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { parseHash } from "../router";
import type { User } from "../types";

const user: User = {
  id: "u1",
  email: "nav@example.org",
  email_verified: true,
  organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
};

const scanList = (items: unknown[]) => ({ items, total: items.length });

function stub(scans: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
      const body =
        path === "/auth/me"
          ? user
          : path === "/scans"
            ? scanList(scans)
            : path === "/targets"
              ? { items: [] }
              : {};
      return { ok: true, status: 200, json: async () => body };
    }),
  );
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

beforeEach(() => {
  window.location.hash = "";
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("routing", () => {
  it("treats an unknown name as not found, and an empty path as Overview", () => {
    expect(parseHash("#/legal/impressum").page).toBe("not-found");
    expect(parseHash("#/nope").page).toBe("not-found");
    expect(parseHash("#/").page).toBe("overview");
    expect(parseHash("").page).toBe("overview");
  });

  it("shows a not-found page with a way home", async () => {
    stub([]);
    window.location.hash = "#/legal/impressum";
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Go to Overview" }),
    ).toHaveAttribute("href", "#/");
  });
});

describe("the browser tab", () => {
  it("names the page the person is on and changes with the page", async () => {
    stub([]);
    window.location.hash = "#/history";
    renderApp();
    await screen.findByRole("heading", { name: "Scan history" });
    expect(document.title).toBe("Scan history – SecureScope");
    window.location.hash = "#/nope";
    await screen.findByRole("heading", { name: "Page not found" });
    expect(document.title).toBe("Page not found – SecureScope");
  });
});

describe("Findings without a scan chosen", () => {
  it("offers the latest scan instead of a dead end", async () => {
    stub([
      {
        id: "latest1",
        target_url: "https://latest.example/",
        host: "latest.example",
        status: "completed",
        score: 80,
        grade: "B",
        created_at: "2026-10-20T10:00:00Z",
        finished_at: "2026-10-20T10:00:01Z",
        counts: {},
      },
    ]);
    window.location.hash = "#/findings";
    renderApp();
    expect(await screen.findByText("latest.example")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open its findings" }),
    ).toHaveAttribute("href", "#/findings?scan=latest1");
  });

  it("says plainly that there are no scans yet", async () => {
    stub([]);
    window.location.hash = "#/findings";
    renderApp();
    expect(await screen.findByText("No scans yet")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open its findings" }),
    ).toBeNull();
  });
});
