import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { auditLabel } from "../format";
import type { AuditEntry, Role, ScanDetail, ScanStatus, User } from "../types";

const base: ScanDetail = {
  id: "abc123",
  target_url: "https://example.org/",
  host: "example.org",
  status: "running",
  score: null,
  grade: null,
  created_at: "2026-10-18T10:00:00Z",
  finished_at: null,
  counts: {},
  error: null,
  metadata: null,
  findings: [],
  score_note: "Heuristic score.",
};
const scanWith = (
  status: ScanStatus,
  extra: Partial<ScanDetail> = {},
): ScanDetail => ({ ...base, status, ...extra });

function userWith(role: Role): User {
  return {
    id: "u1",
    email: "alice@example.org",
    email_verified: true,
    organizations: [{ id: "org1", name: "Alice Org", slug: "alice-org", role }],
  };
}

interface Call {
  url: string;
  method: string;
}

type Handler = (
  url: string,
  method: string,
) => { status?: number; body: unknown };

function mockApi(
  handler: Handler,
  role: Role = "OWNER",
  overview: unknown = { sites: [], fix_first: null, other_open: 0 },
): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });
      if (url.endsWith("/auth/me"))
        return { ok: true, status: 200, json: async () => userWith(role) };
      if (url.endsWith("/targets"))
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
      if (url.endsWith("/overview")) {
        return { ok: true, status: 200, json: async () => overview };
      }
      const { status = 200, body } = handler(url, method);
      return { ok: status < 400, status, json: async () => body };
    }),
  );
  return calls;
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

describe("cancelling and retrying from a scan", () => {
  it("cancels a running scan and then offers a retry", async () => {
    let current = scanWith("running");
    const calls = mockApi((url, method) => {
      if (method === "POST" && url.endsWith("/scans/abc123/cancel")) {
        current = scanWith("cancelled", {
          error: "Cancelled before it finished.",
        });
        return { body: current };
      }
      return { body: current };
    });
    window.location.hash = "#/?scan=abc123";
    renderApp();
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Cancel scan" }),
    );

    expect(
      await screen.findByRole("button", { name: "Retry scan" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel scan" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/This scan was cancelled before it finished/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Scan cancelled. No findings were recorded."),
    ).toBeInTheDocument();
    expect(
      calls.some(
        (c) => c.method === "POST" && c.url.endsWith("/scans/abc123/cancel"),
      ),
    ).toBe(true);
  });

  it("retries a failed scan and opens the new one", async () => {
    const calls = mockApi((url, method) => {
      if (method === "POST" && url.endsWith("/scans/abc123/retry")) {
        return { status: 202, body: scanWith("queued", { id: "newscan9" }) };
      }
      if (url.endsWith("/scans/newscan9"))
        return { body: scanWith("queued", { id: "newscan9" }) };
      return {
        body: scanWith("failed", { error: "The connection timed out." }),
      };
    });
    window.location.hash = "#/?scan=abc123";
    renderApp();
    const user = userEvent.setup();

    expect(
      await screen.findByText("The connection timed out."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry scan" }));

    await waitFor(() => expect(window.location.hash).toBe("#/?scan=newscan9"));
    expect(
      calls.some(
        (c) => c.method === "POST" && c.url.endsWith("/scans/abc123/retry"),
      ),
    ).toBe(true);
  });

  it("shows the server's reason when a retry is refused", async () => {
    mockApi((_url, method) =>
      method === "POST"
        ? {
            status: 403,
            body: { detail: "Ownership of example.org has not been verified." },
          }
        : { body: scanWith("failed", { error: "Timed out." }) },
    );
    window.location.hash = "#/?scan=abc123";
    renderApp();
    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Retry scan" }));
    expect(
      await screen.findByText(/has not been verified/),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/?scan=abc123");
  });

  it("offers neither action to a role that cannot start scans", async () => {
    mockApi(
      () => ({ body: scanWith("failed", { error: "Timed out." }) }),
      "VIEWER",
    );
    window.location.hash = "#/?scan=abc123";
    renderApp();
    expect(await screen.findByText("Timed out.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Retry scan" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel scan" }),
    ).not.toBeInTheDocument();
  });

  it("offers a PDF export next to the other formats once a scan is complete", async () => {
    mockApi(() => ({ body: scanWith("completed", { score: 90, grade: "A" }) }));
    window.location.hash = "#/?scan=abc123";
    renderApp();
    const group = await screen.findByRole("group", { name: "Export report" });
    // The PDF is made on request and downloaded through a short-lived link, so it is a button.
    expect(
      within(group).getByRole("button", { name: "Download PDF report" }),
    ).toBeInTheDocument();
    expect(
      within(group)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["HTML", "Markdown", "JSON", "CSV", "Compare with another scan"]);
  });
});

describe("scan history actions", () => {
  const rows = ["running", "failed", "cancelled", "completed"].map(
    (status, i) => ({
      ...base,
      id: `scan${i}`,
      host: `${status}.example.org`,
      status,
      counts: {},
    }),
  );

  it("shows Cancel only for active scans and Retry only for failed or cancelled ones", async () => {
    mockApi(() => ({ body: { items: rows, total: rows.length } }));
    window.location.hash = "#/history";
    renderApp();
    expect(
      await screen.findByRole("button", {
        name: "Cancel scan of running.example.org",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry scan of failed.example.org" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Retry scan of cancelled.example.org",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Scan again of completed.example.org",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Cancel scan of completed/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Retry scan of running/ }),
    ).not.toBeInTheDocument();
  });

  it("cancels from the list and reloads it", async () => {
    let state = "running";
    const calls = mockApi((_url, method) => {
      if (method === "POST") {
        state = "cancelled";
        return { body: { ...base, status: "cancelled" } };
      }
      return { body: { items: [{ ...base, status: state }], total: 1 } };
    });
    window.location.hash = "#/history";
    renderApp();
    await userEvent.setup().click(
      await screen.findByRole("button", {
        name: "Cancel scan of example.org",
      }),
    );
    expect(
      await screen.findByRole("button", { name: "Retry scan of example.org" }),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.url.includes("/scans?limit=")).length).toBe(2);
  });
});

describe("audit log", () => {
  const entries: AuditEntry[] = [
    {
      id: "e2",
      timestamp: "2026-10-18T11:00:00Z",
      event_type: "scan.cancelled",
      actor_user_id: "u1",
      actor_email: "alice@example.org",
      resource_type: "scan",
      resource_id: "abcdef1234567890",
      request_id: "req12345678",
    },
    {
      id: "e1",
      timestamp: "2026-10-18T10:00:00Z",
      event_type: "something.new",
      actor_user_id: null,
      actor_email: null,
      resource_type: null,
      resource_id: null,
      request_id: null,
    },
  ];

  it("lists events with readable names, who did them and a link to the scan", async () => {
    const calls = mockApi(() => ({
      body: {
        items: entries,
        total: 2,
        event_types: ["scan.cancelled", "something.new"],
      },
    }));
    window.location.hash = "#/audit";
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Audit log" }),
    ).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Scan cancelled")).toBeInTheDocument();
    expect(within(table).getByText("alice@example.org")).toBeInTheDocument();
    expect(within(table).getByText("No user recorded")).toBeInTheDocument();
    expect(within(table).getByText("something.new")).toBeInTheDocument(); // unknown types are not hidden
    expect(
      within(table).getByRole("link", { name: "Open scan abcdef12" }),
    ).toHaveAttribute("href", "#/findings?scan=abcdef1234567890");
    expect(screen.getByText("Showing 2 of 2 events.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Audit log" })).toBeInTheDocument(); // in the navigation
    expect(calls.filter((c) => c.url.includes("/audit-events")).length).toBe(1);
  });

  it("filters by event type on the server", async () => {
    const calls = mockApi((url) => ({
      body: {
        items: url.includes("event_type=scan.cancelled")
          ? [entries[0]]
          : entries,
        total: url.includes("event_type=scan.cancelled") ? 1 : 2,
        event_types: ["scan.cancelled", "something.new"],
      },
    }));
    window.location.hash = "#/audit";
    renderApp();
    await userEvent
      .setup()
      .selectOptions(await screen.findByLabelText("Event"), "scan.cancelled");
    expect(
      await screen.findByText("Showing 1 of 1 events."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("event_type=scan.cancelled"))).toBe(
      true,
    );
  });

  it("loads further pages from where the list ended", async () => {
    const first = entries[0] as AuditEntry;
    const page = (n: number, tag: string): AuditEntry[] =>
      Array.from({ length: n }, (_, i) => ({ ...first, id: `${tag}-${i}` }));
    const calls = mockApi((url) =>
      url.includes("offset=0")
        ? { body: { items: page(25, "a"), total: 30, event_types: [] } }
        : { body: { items: page(5, "b"), total: 30, event_types: [] } },
    );
    window.location.hash = "#/audit";
    renderApp();
    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Load more" }));
    expect(
      await screen.findByText("Showing 30 of 30 events."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("offset=25"))).toBe(true);
    expect(
      screen.queryByRole("button", { name: "Load more" }),
    ).not.toBeInTheDocument();
  });

  it.each<Role>(["SECURITY_ANALYST", "MEMBER", "VIEWER"])(
    "is hidden from %s",
    async (role) => {
      const calls = mockApi(
        () => ({ body: { items: [], total: 0, event_types: [] } }),
        role,
      );
      window.location.hash = "#/audit";
      renderApp();
      expect(
        await screen.findByText(/cannot view the audit log/),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Audit log" }),
      ).not.toBeInTheDocument();
      expect(calls.some((c) => c.url.includes("/audit-events"))).toBe(false);
    },
  );

  it("shows the server's message if the request is refused", async () => {
    mockApi(() => ({
      status: 403,
      body: { detail: "Your role does not allow this action." },
    }));
    window.location.hash = "#/audit";
    renderApp();
    expect(
      await screen.findByText("Your role does not allow this action."),
    ).toBeInTheDocument();
  });

  it("names every event the backend records", () => {
    for (const type of [
      "scan.created",
      "scan.cancelled",
      "scan.retried",
      "report.exported",
      "finding.status_changed",
      "org.member.added",
      "target.verified",
      "auth.login.success",
      "auth.session.refreshed",
      "auth.password_reset.requested",
      "auth.password_reset.completed",
    ]) {
      expect(auditLabel(type)).not.toBe(type);
    }
    expect(auditLabel("future.event")).toBe("future.event");
  });
});

describe("scanning again", () => {
  const site = {
    host: "example.org",
    latest_scan_id: "abc123",
    score: 80,
    grade: "B",
    scanned_at: "2026-10-18T10:00:00Z",
    previous_score: null,
    score_change: null,
    open_counts: {},
    open_total: 0,
    top_finding: null,
    history: [],
  };
  const overview = { sites: [site], fix_first: null, other_open: 0 };

  it("starts a new scan from a site card and opens it", async () => {
    const calls = mockApi(
      (url, method) =>
        method === "POST" && url.endsWith("/scans/abc123/retry")
          ? { status: 202, body: scanWith("queued", { id: "new456" }) }
          : { body: scanWith("completed") },
      "OWNER",
      overview,
    );
    renderApp();
    await userEvent.setup().click(
      await screen.findByRole("button", {
        name: "Scan again of example.org",
      }),
    );
    await waitFor(() => expect(window.location.hash).toContain("new456"));
    expect(
      calls.some(
        (c) => c.method === "POST" && c.url.endsWith("/scans/abc123/retry"),
      ),
    ).toBe(true);
  });

  it("shows the reason when the server refuses, for example a rate limit", async () => {
    mockApi(
      (_url, method) =>
        method === "POST"
          ? {
              status: 429,
              body: { detail: "You are scanning this site too often." },
            }
          : { body: {} },
      "OWNER",
      overview,
    );
    renderApp();
    await userEvent.setup().click(
      await screen.findByRole("button", {
        name: "Scan again of example.org",
      }),
    );
    expect(await screen.findByText(/too often/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Scan again of example.org" }),
    ).toBeEnabled();
  });

  it("is not offered to viewers", async () => {
    mockApi(() => ({ body: {} }), "VIEWER", overview);
    renderApp();
    expect(
      await screen.findByRole("list", { name: "Your sites" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Scan again/ }),
    ).not.toBeInTheDocument();
  });
});
