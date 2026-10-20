import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { FixFirstPanel } from "../components/Posture";
import SummaryCards from "../components/SummaryCards";
import type { Overview, SitePosture, Target, User } from "../types";

const user: User = {
  id: "u1",
  email: "alice@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "Alice Org", slug: "alice-org", role: "OWNER" },
  ],
};

function mockApi(me: User | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) {
        return me
          ? { ok: true, status: 200, json: async () => me }
          : { ok: false, status: 401, json: async () => ({ detail: "no" }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], sites: [], fix_first: null }),
      };
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
  vi.unstubAllGlobals();
});

const site = (over: Partial<SitePosture>): SitePosture => ({
  host: "a.example",
  latest_scan_id: "s1",
  score: 90,
  grade: "A",
  scanned_at: "2026-10-20T10:00:00Z",
  previous_score: null,
  score_change: null,
  open_counts: {},
  open_total: 0,
  top_finding: null,
  history: [],
  ...over,
});

const verified = (hostname: string) =>
  ({ hostname, status: "verified" }) as unknown as Target;

describe("summary cards", () => {
  it("adds up real numbers from the overview and the targets", () => {
    const overview: Overview = {
      sites: [
        site({ score: 70, open_total: 3, open_counts: { high: 1, low: 2 } }),
        site({
          host: "b.example",
          score: 95,
          open_total: 1,
          open_counts: { critical: 1 },
        }),
      ],
      fix_first: null,
      other_open: 0,
    };
    render(
      <SummaryCards
        overview={overview}
        targets={[verified("a.example"), verified("b.example")]}
      />,
    );
    const values = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent ?? "");
    expect(values[0]).toContain("Verified sites2");
    expect(values[1]).toContain("Open findings4");
    expect(values[2]).toContain("Critical and high2");
    expect(values[3]).toContain("Lowest heuristic score70");
  });

  it("shows a dash instead of inventing a score when nothing was scanned", () => {
    render(
      <SummaryCards
        overview={{ sites: [], fix_first: null, other_open: 0 }}
        targets={[]}
      />,
    );
    expect(
      screen.getByText("Lowest heuristic score").parentElement,
    ).toHaveTextContent("–");
  });
});

describe("fix this first", () => {
  const base = {
    host: "a.example",
    scan_id: "s1",
    finding_id: "SS-DISC-SRV-002",
    title: "Server header is present",
    confidence: "high" as const,
    remediation: "Consider removing the Server header.",
  };

  it("says nothing is urgent when only informational notes are open", () => {
    render(
      <FixFirstPanel
        overview={{
          sites: [],
          fix_first: { ...base, severity: "info" },
          other_open: 0,
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Nothing urgent" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Fix this first")).not.toBeInTheDocument();
  });

  it("keeps the urgent heading for real findings", () => {
    render(
      <FixFirstPanel
        overview={{
          sites: [],
          fix_first: { ...base, severity: "medium" },
          other_open: 0,
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Fix this first" }),
    ).toBeInTheDocument();
  });
});

describe("legal pages", () => {
  it("open for a signed-out visitor and link back to sign in", async () => {
    mockApi(null);
    window.location.hash = "#/privacy";
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Privacy notice" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to sign in" }),
    ).toHaveAttribute("href", "#/login");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute(
      "href",
      "#/terms",
    );
  });

  it("link back to the app when someone is signed in", async () => {
    mockApi(user);
    window.location.hash = "#/terms";
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Terms of use" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "Back to the app" }),
    ).toHaveAttribute("href", "#/");
  });

  it("never wait for the account check before showing", () => {
    // /auth/me never answers; the legal page must still render.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => undefined)),
    );
    window.location.hash = "#/impressum";
    renderApp();
    expect(
      screen.getByRole("heading", { name: "Impressum" }),
    ).toBeInTheDocument();
  });
});

describe("signed-in visitors on the sign-in page", () => {
  it("are sent to the overview", async () => {
    mockApi(user);
    window.location.hash = "#/login";
    renderApp();
    await waitFor(() => expect(window.location.hash).toBe("#/"));
    expect(
      await screen.findByRole("heading", { name: "Overview" }),
    ).toBeInTheDocument();
  });
});
