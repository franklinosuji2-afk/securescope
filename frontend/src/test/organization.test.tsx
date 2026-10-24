import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import type { Overview, ScanSummary, Target, User } from "../types";

/**
 * A person in two organizations. The stubbed server answers like the real one: the organization is the
 * X-Organization-Id header, and without it the first membership (org1). Each organization's data names
 * its own host, so any data from the wrong organization is visible on the page.
 */
const me: User = {
  id: "u1",
  email: "multi@example.org",
  email_verified: true,
  organizations: [
    { id: "org1", name: "First Org", slug: "first-org", role: "OWNER" },
    { id: "org2", name: "Second Org", slug: "second-org", role: "OWNER" },
  ],
};

const hostOf = (org: string) => `site-${org}.example`;

const target = (org: string): Target => ({
  id: `t${org}`,
  hostname: hostOf(org),
  status: "verified",
  challenge_token: "a".repeat(32),
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: "2026-10-18T10:00:00Z",
  verification_method: "dns_txt",
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: "x",
  dns_record_value: "x",
  http_file_url: "x",
  http_file_content: "x",
});

const overview = (org: string): Overview => ({
  sites: [
    {
      host: hostOf(org),
      latest_scan_id: `scan${org}`,
      score: org === "org1" ? 41 : 92,
      grade: org === "org1" ? "F" : "A",
      scanned_at: "2026-10-18T12:00:00Z",
      previous_score: null,
      score_change: null,
      open_counts: {},
      open_total: 0,
      top_finding: null,
      history: [],
    },
  ],
  fix_first: null,
  other_open: 0,
  scanned_hosts: [hostOf(org)],
});

const scans = (org: string): { items: ScanSummary[]; total: number } => ({
  items: [
    {
      id: `scan${org}`,
      target_url: `https://${hostOf(org)}/`,
      host: hostOf(org),
      status: "completed",
      score: 50,
      grade: "D",
      created_at: "2026-10-18T12:00:00Z",
      finished_at: "2026-10-18T12:00:01Z",
      counts: {},
    },
  ],
  total: 1,
});

interface Call {
  path: string;
  org: string | null;
}

/** Answers per organization. `hold(org, path)` returns a release function that answers a held request. */
function mockServer() {
  const calls: Call[] = [];
  const held = new Map<string, () => void>();
  const holding = new Set<string>();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const sent = headers["X-Organization-Id"] ?? null;
      calls.push({ path, org: sent });
      if (path === "/auth/me")
        return { ok: true, status: 200, json: async () => me };
      const org = sent ?? "org1"; // the server's default: the first membership
      if (path.startsWith("/scans/")) {
        const own = scans(org).items[0]!;
        if (path !== `/scans/${own.id}`)
          return {
            ok: false,
            status: 404,
            json: async () => ({ detail: "Scan not found." }),
          };
        const detail = {
          ...own,
          error: null,
          metadata: null,
          findings: [],
          score_note: "",
        };
        return { ok: true, status: 200, json: async () => detail };
      }
      const body =
        path === "/targets"
          ? { items: [target(org)] }
          : path === "/overview"
            ? overview(org)
            : path === "/scans"
              ? scans(org)
              : {};
      const response = { ok: true, status: 200, json: async () => body };
      const key = `${org} ${path}`;
      if (holding.has(key)) {
        holding.delete(key);
        return new Promise((resolve) => held.set(key, () => resolve(response)));
      }
      return response;
    }),
  );
  return {
    calls,
    hold: (org: string, path: string) => holding.add(`${org} ${path}`),
    release: (org: string, path: string) => held.get(`${org} ${path}`)?.(),
  };
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

/** The dashboard request paths, with the organization each was sent for. */
const dashboardCalls = (calls: Call[]) =>
  calls.filter((c) => ["/targets", "/overview", "/scans"].includes(c.path));

beforeEach(() => {
  window.location.hash = "";
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("a person in several organizations", () => {
  it("loads every card for the stored organization from the very first request", async () => {
    window.sessionStorage.setItem("securescope.org", "org2");
    const server = mockServer();
    renderApp();

    expect(await screen.findByText("Score 92, grade A")).toBeInTheDocument();
    await within(
      screen.getByRole("region", { name: "Scan activity" }),
    ).findByRole("link", { name: /site-org2\.example/ });
    expect(screen.queryByText(/site-org1/)).not.toBeInTheDocument();
    const calls = dashboardCalls(server.calls);
    expect(calls.length).toBeGreaterThanOrEqual(3);
    expect(calls.filter((c) => c.org !== "org2")).toEqual([]);
    expect(
      screen.getByRole("button", {
        name: "Download PDF report for site-org2.example",
      }),
    ).toBeInTheDocument();
  });

  it("reloads everything for the new organization after a switch", async () => {
    const server = mockServer();
    window.location.hash = "#/?scan=scanorg1";
    renderApp();
    expect(await screen.findByText("Score 41, grade F")).toBeInTheDocument();
    // Wait for the first organization's initial dashboard requests to be complete before taking the
    // snapshot; on a slow machine the scan list can still be requested after the score has rendered.
    await waitFor(() =>
      expect(new Set(dashboardCalls(server.calls).map((c) => c.path))).toEqual(
        new Set(["/targets", "/overview", "/scans"]),
      ),
    );
    await new Promise((resolve) => setTimeout(resolve, 50));
    const before = server.calls.length;

    await userEvent.selectOptions(
      screen.getByLabelText("Active organization"),
      "org2",
    );

    expect(await screen.findByText("Score 92, grade A")).toBeInTheDocument();
    await within(
      screen.getByRole("region", { name: "Scan activity" }),
    ).findByRole("link", { name: /site-org2\.example/ });
    expect(screen.queryByText(/site-org1|Score 41/)).not.toBeInTheDocument();
    const after = dashboardCalls(server.calls.slice(before));
    expect(new Set(after.map((c) => c.path))).toEqual(
      new Set(["/targets", "/overview", "/scans"]),
    );
    expect(after.filter((c) => c.org !== "org2")).toEqual([]);
    // The scan in the address belonged to the first organization, so it is dropped.
    expect(window.location.hash).toBe("#/");
    expect(
      server.calls.some(
        (c) => c.path === "/scans/scanorg1" && c.org === "org2",
      ),
    ).toBe(false);
    expect(
      screen.getByRole("button", {
        name: "Download PDF report for site-org2.example",
      }),
    ).toBeInTheDocument();
  });

  it("ignores a slow answer for the organization that was left", async () => {
    const server = mockServer();
    server.hold("org1", "/overview");
    renderApp();
    const select = await screen.findByLabelText("Active organization");
    await waitFor(() =>
      expect(server.calls.some((c) => c.path === "/overview")).toBe(true),
    );

    await userEvent.selectOptions(select, "org2");
    expect(await screen.findByText("Score 92, grade A")).toBeInTheDocument();

    server.release("org1", "/overview"); // the first organization's answer arrives late
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByText("Score 92, grade A")).toBeInTheDocument();
    expect(screen.queryByText(/site-org1|Score 41/)).not.toBeInTheDocument();
  });
});
