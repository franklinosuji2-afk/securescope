import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import FindingDetail from "../components/FindingDetail";
import type { Finding, Role, ScanDetail, User } from "../types";

const finding: Finding = {
  id: "SS-HDR-CSP-001",
  title: "Content-Security-Policy header missing",
  severity: "medium",
  category: "Security headers",
  description: "d",
  evidence: null,
  remediation: "r",
  confidence: "high",
  fingerprint: "f".repeat(16),
  status: "open",
  status_note: null,
  first_seen_at: null,
  last_seen_at: null,
};
const scan: ScanDetail = {
  id: "abc123",
  target_url: "https://example.org/",
  host: "example.org",
  status: "completed",
  score: 80,
  grade: "B",
  created_at: "2026-10-18T10:00:00Z",
  finished_at: "2026-10-18T10:00:02Z",
  counts: { medium: 1 },
  error: null,
  metadata: null,
  findings: [finding],
  score_note: "n",
};
const user = (role: Role): User => ({
  id: "u1",
  email: "a@example.org",
  email_verified: true,
  organizations: [{ id: "org1", name: "Org", slug: "org", role }],
});

function serve(role: Role, recheck: { status: number; body: unknown }) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/me"))
        return { ok: true, status: 200, json: async () => user(role) };
      if (url.includes("/recheck")) {
        calls.push(`${init?.method} ${url}`);
        return {
          ok: recheck.status < 400,
          status: recheck.status,
          json: async () => recheck.body,
        };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    }),
  );
  return calls;
}

function show(s: ScanDetail = scan) {
  return render(
    <AuthProvider>
      <FindingDetail scan={s} finding={finding} />
    </AuthProvider>,
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("Check if it is fixed", () => {
  it("reports each outcome in plain words and posts to the finding's re-check route", async () => {
    const calls = serve("OWNER", {
      status: 200,
      body: {
        finding_id: finding.id,
        host: "example.org",
        outcome: "not_seen",
        message:
          "This check no longer reports it. Run a full scan to update the score and mark it resolved.",
        checked_at: "2026-10-26T10:00:00Z",
        evidence: null,
      },
    });
    show();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Check this finding again" }),
    );
    const result = await screen.findByTestId("recheck-result");
    expect(result).toHaveTextContent("Not seen this time.");
    expect(result).toHaveTextContent("Run a full scan");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatch(
      /^POST .*\/scans\/abc123\/findings\/SS-HDR-CSP-001\/recheck$/,
    );
  });

  it("never says fixed when it could not check, and shows a refusal from the server", async () => {
    serve("OWNER", {
      status: 429,
      body: {
        detail: "This site was checked too often recently. Try again later.",
      },
    });
    show();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Check this finding again" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "checked too often",
    );
    expect(screen.queryByTestId("recheck-result")).toBeNull();
  });

  it("is not offered to viewers or for a scan that has not finished", async () => {
    serve("VIEWER", { status: 200, body: {} });
    const first = show();
    await screen.findByRole("heading", { name: /Status/ });
    expect(
      screen.queryByRole("button", { name: "Check this finding again" }),
    ).toBeNull();
    first.unmount();
    serve("OWNER", { status: 200, body: {} });
    show({ ...scan, status: "running" });
    await screen.findByRole("heading", { name: /Status/ });
    expect(
      screen.queryByRole("button", { name: "Check this finding again" }),
    ).toBeNull();
  });
});
