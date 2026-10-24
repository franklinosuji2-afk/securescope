import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { attention, duration } from "../pages/Health";
import type { PlatformHealth, User } from "../types";

const admin: User = {
  id: "u1",
  email: "boss@example.org",
  email_verified: true,
  is_admin: true,
  organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
};

const health = (over: Partial<PlatformHealth> = {}): PlatformHealth => ({
  version: "0.8.0",
  started_at: "2026-10-20T10:00:00Z",
  uptime_seconds: 3700,
  database: { ok: true, latency_ms: 12 },
  requests: {
    window_seconds: 3600,
    requests: 40,
    server_errors: 0,
    client_errors: 2,
    error_rate: 0,
    p50_ms: 40,
    p95_ms: 180,
    p99_ms: 400,
    routes: [{ route: "/api/v1/scans", requests: 30, errors: 0, p95_ms: 200 }],
    truncated: false,
  },
  scans: {
    window_hours: 24,
    completed: 3,
    failed: 1,
    cancelled: 0,
    in_progress: 0,
    avg_seconds: 4.2,
    max_concurrent: 3,
    running_here: 0,
  },
  mail: {
    provider: "brevo",
    delivering: true,
    sent: 5,
    failed: 0,
    last_success_at: "2026-10-20T12:00:00Z",
    last_failure_at: null,
    last_failure_status: null,
  },
  configuration: {
    trusted_proxy: true,
    admin_email: true,
    analytics_enabled: true,
    metrics_endpoint: false,
    cookie_secure: true,
    verification_valid_days: 180,
    retention_days: 30,
  },
  ...over,
});

function mockApi(me: User, h: PlatformHealth) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (...args: [url: string, init?: RequestInit]) => {
      const url = args[0];
      if (url.endsWith("/auth/me"))
        return { ok: true, status: 200, json: async () => me };
      if (url.endsWith("/platform/health"))
        return { ok: true, status: 200, json: async () => h };
      if (url.endsWith("/feedback/summary"))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            count: 2,
            average: 4.5,
            by_rating: { "5": 1, "4": 1 },
            by_plan: {
              Agency: { count: 1, average: 5 },
              Free: { count: 1, average: 4 },
            },
            latest: [
              {
                plan: "Agency",
                rating: 5,
                category: "reports",
                message: "Great reports",
                created_at: "2026-10-24T10:00:00Z",
                updated_at: "2026-10-24T10:00:00Z",
              },
            ],
          }),
        };
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [], sites: [], fix_first: null }),
      };
    }),
  );
}

beforeEach(() => {
  window.location.hash = "";
  vi.unstubAllGlobals();
});

describe("platform health page", () => {
  it("shows measured values and no problems when all is well", async () => {
    mockApi(admin, health());
    window.location.hash = "#/health";
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(await screen.findByText("No problems detected")).toBeInTheDocument();
    expect(screen.getByText("Reachable")).toBeInTheDocument();
    expect(screen.getByText("180 ms")).toBeInTheDocument();
    expect(screen.getByText("/api/v1/scans")).toBeInTheDocument();
    expect(screen.getByText("4.2 s")).toBeInTheDocument();
  });

  it("shows the private feedback summary to the operator", async () => {
    mockApi(admin, health());
    window.location.hash = "#/health";
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(await screen.findByText("Customer feedback")).toBeInTheDocument();
    expect(await screen.findByText("Great reports")).toBeInTheDocument();
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(
      screen.getByText(/Agency 5\.0 \(1\) · Free 4\.0 \(1\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/5★ · Agency · Reports/)).toBeInTheDocument();
  });

  it("is not offered to ordinary accounts", async () => {
    mockApi({ ...admin, is_admin: false }, health());
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    await screen.findByRole("navigation", { name: "Primary" });
    expect(screen.queryByRole("link", { name: "Platform Health" })).toBeNull();
  });

  it("offers the page to the operator", async () => {
    mockApi(admin, health());
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(
      await screen.findByRole("link", { name: "Platform Health" }),
    ).toBeInTheDocument();
  });
});

describe("attention rules", () => {
  it("flags only what was measured", () => {
    expect(attention(health())).toEqual([]);
    expect(
      attention(health({ database: { ok: false, latency_ms: null } })),
    ).toContain("The database did not answer.");
    const few = health();
    few.requests = {
      ...few.requests,
      requests: 5,
      server_errors: 5,
      error_rate: 1,
    };
    expect(attention(few)).toEqual([]); // too few requests to call it a rate
    const many = health();
    many.requests = {
      ...many.requests,
      requests: 100,
      server_errors: 20,
      error_rate: 0.2,
    };
    expect(attention(many)[0]).toMatch(/20% of recent requests/);
  });

  it("notices a failing mail provider and log-only mail", () => {
    const failing = health();
    failing.mail = {
      ...failing.mail,
      last_failure_at: "2026-10-20T13:00:00Z",
      last_failure_status: 401,
    };
    expect(attention(failing)[0]).toMatch(/last email send failed.*401/);
    const logOnly = health();
    logOnly.mail = { ...logOnly.mail, delivering: false, provider: "log" };
    expect(attention(logOnly)[0]).toMatch(/not being delivered/);
  });

  it("formats durations", () => {
    expect(duration(5)).toBe("5 s");
    expect(duration(125)).toBe("2 min");
    expect(duration(3700)).toBe("1 h 1 min");
    expect(duration(3600)).toBe("1 h");
    expect(duration(200000)).toBe("2 days 7 h");
  });
});
