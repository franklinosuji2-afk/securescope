import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { change } from "../pages/Analytics";
import type { AnalyticsSummary, User } from "../types";

const base: User = {
  id: "u1",
  email: "boss@example.org",
  email_verified: true,
  organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
};

const day = (date: string, views: number, visitors: number) => ({
  date,
  views,
  visitors,
});

const summary = (over: Partial<AnalyticsSummary> = {}): AnalyticsSummary => ({
  range_days: 7,
  timezone: "UTC",
  tracking_enabled: true,
  last_event_at: "2026-10-20T10:00:00Z",
  current: {
    views: 12,
    visitors: 5,
    series: [day("2026-10-19", 4, 2), day("2026-10-20", 8, 3)],
  },
  previous: { views: 6, visitors: 5, series: [] },
  today: { views: 8, visitors: 3 },
  yesterday: { views: 4, visitors: 2 },
  top_pages: [{ name: "login", count: 7, visitors: 4 }],
  landing_pages: [{ name: "privacy", count: 2 }],
  sources: [{ name: "Direct", count: 4 }],
  devices: [{ name: "mobile", count: 1 }],
  ...over,
});

function mockApi(me: User | null, analytics: AnalyticsSummary = summary()) {
  const fetchMock = vi.fn(
    async (...args: [url: string, init?: RequestInit]) => {
      const url = args[0];
      if (url.endsWith("/auth/me")) {
        return me
          ? { ok: true, status: 200, json: async () => me }
          : { ok: false, status: 401, json: async () => ({ detail: "no" }) };
      }
      if (url.includes("/analytics/summary")) {
        return { ok: true, status: 200, json: async () => analytics };
      }
      if (url.includes("/analytics/collect")) {
        return { ok: true, status: 204, json: async () => ({}) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], sites: [], fix_first: null }),
      };
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const collectCalls = (m: ReturnType<typeof mockApi>) =>
  m.mock.calls.filter((c) => String(c[0]).includes("/analytics/collect"));

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
afterEach(() => vi.unstubAllGlobals());

describe("visit counting", () => {
  it("counts a signed-out visit to a public page once, with only the page name", async () => {
    const m = mockApi(null);
    window.location.hash = "#/privacy";
    renderApp();
    await waitFor(() => expect(collectCalls(m)).toHaveLength(1));
    const init = collectCalls(m)[0]![1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ page: "privacy" });
    expect(init.credentials).toBe("omit");
  });

  it("never counts someone who is signed in", async () => {
    const m = mockApi(base);
    window.location.hash = "#/privacy";
    renderApp();
    await screen.findByRole("heading", { name: "Privacy notice" });
    await new Promise((r) => setTimeout(r, 50));
    expect(collectCalls(m)).toHaveLength(0);
  });

  it("does not count a visitor who sends Do Not Track", async () => {
    const m = mockApi(null);
    Object.defineProperty(navigator, "doNotTrack", {
      value: "1",
      configurable: true,
    });
    window.location.hash = "#/login";
    renderApp();
    await screen.findByRole("heading", { name: /sign in/i });
    await new Promise((r) => setTimeout(r, 50));
    expect(collectCalls(m)).toHaveLength(0);
    Reflect.deleteProperty(navigator, "doNotTrack");
  });
});

describe("analytics page", () => {
  it("is not offered to ordinary accounts", async () => {
    mockApi(base);
    renderApp();
    await screen.findByRole("navigation", { name: "Primary" });
    expect(screen.queryByRole("link", { name: "Analytics" })).toBeNull();
  });

  it("shows the real numbers to the operator", async () => {
    mockApi({ ...base, is_admin: true });
    window.location.hash = "#/analytics";
    renderApp();
    await screen.findByRole("heading", { name: "Website analytics" });
    expect(await screen.findByText("Visitors today")).toBeInTheDocument();
    expect(screen.getByText("Sign in")).toBeInTheDocument();
    expect(screen.getAllByText("Direct").length).toBeGreaterThan(0);
    expect(screen.getByText(/no cookies, no stored ip/i)).toBeInTheDocument();
    expect(screen.queryByText("No visits recorded yet")).toBeNull();
  });

  it("explains an empty period instead of showing sample data", async () => {
    mockApi(
      { ...base, is_admin: true },
      summary({
        last_event_at: null,
        current: { views: 0, visitors: 0, series: [day("2026-10-20", 0, 0)] },
        previous: { views: 0, visitors: 0, series: [] },
        today: { views: 0, visitors: 0 },
        yesterday: { views: 0, visitors: 0 },
        top_pages: [],
        landing_pages: [],
        sources: [],
        devices: [],
      }),
    );
    window.location.hash = "#/analytics";
    renderApp();
    expect(
      await screen.findByText("No visits recorded yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no visit has been recorded yet/i),
    ).toBeInTheDocument();
  });

  it("asks again when another range is chosen", async () => {
    const m = mockApi({ ...base, is_admin: true });
    window.location.hash = "#/analytics";
    renderApp();
    await screen.findByText("Visitors today");
    await userEvent.click(screen.getByRole("button", { name: "30 days" }));
    await waitFor(() =>
      expect(m.mock.calls.some((c) => String(c[0]).includes("days=30"))).toBe(
        true,
      ),
    );
  });
});

describe("change text", () => {
  it("is honest when there is nothing to compare", () => {
    expect(change(5, 0)).toBe("no earlier data");
    expect(change(0, 0)).toBe("no change");
    expect(change(15, 10)).toBe("+50% vs previous period");
    expect(change(5, 10)).toBe("-50% vs previous period");
  });
});

describe("email confirmation", () => {
  it("lets an unconfirmed account ask for a new confirmation email", async () => {
    const m = mockApi({ ...base, email_verified: false });
    renderApp();
    await userEvent.click(
      await screen.findByRole("button", { name: "Send the email again" }),
    );
    expect(await screen.findByText(/^Sent\./)).toBeInTheDocument();
    expect(
      m.mock.calls.some((c) =>
        String(c[0]).endsWith("/auth/resend-verification"),
      ),
    ).toBe(true);
  });
});
