import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import BentoGrid from "../components/bento/BentoGrid";
import {
  priorityActions,
  scanOutcome,
  scanRecord,
  scoreScope,
  topIssues,
  weakestSite,
} from "../components/bento/bentoLogic";
import SummaryCards from "../components/SummaryCards";
import type {
  Overview,
  ScanSummary,
  SitePosture,
  Target,
  TopFinding,
} from "../types";

const top = (host: string, severity: TopFinding["severity"]): TopFinding => ({
  host,
  scan_id: `scan-${host}`,
  finding_id: "SS-HDR-HSTS-001",
  title: `Finding on ${host}`,
  severity,
  confidence: "high",
  remediation: "Fix it.",
});

const site = (host: string, over: Partial<SitePosture> = {}): SitePosture => ({
  host,
  latest_scan_id: `scan-${host}`,
  score: 80,
  grade: "B",
  scanned_at: "2026-10-18T12:00:00Z",
  previous_score: null,
  score_change: null,
  open_counts: {},
  open_total: 0,
  top_finding: null,
  history: [],
  ...over,
});

const target = (hostname: string, status: Target["status"]): Target => ({
  id: hostname,
  hostname,
  status,
  challenge_token: "a".repeat(32),
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: null,
  verification_method: null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: "",
  dns_record_value: "",
  http_file_url: "",
  http_file_content: "",
});

const scan = (
  id: string,
  host: string,
  status: ScanSummary["status"],
  created = "2026-10-18T12:00:00Z",
): ScanSummary => ({
  id,
  target_url: `https://${host}/`,
  host,
  status,
  score: status === "completed" ? 70 : null,
  grade: null,
  created_at: created,
  finished_at: created,
  counts: status === "completed" ? { high: 1, low: 2 } : {},
});

describe("bento rules", () => {
  it("picks the lowest score and ignores unscored sites", () => {
    const sites = [
      site("a.test", { score: 90 }),
      site("b.test", { score: 55 }),
      site("c.test", { score: null }),
    ];
    expect(weakestSite(sites)?.host).toBe("b.test");
    expect(weakestSite([site("c.test", { score: null })])).toBeNull();
    expect(weakestSite([])).toBeNull();
  });

  it("orders top issues by severity then host and skips sites without one", () => {
    const sites = [
      site("z.test", { top_finding: top("z.test", "high") }),
      site("a.test", { top_finding: top("a.test", "high") }),
      site("m.test", { top_finding: top("m.test", "critical") }),
      site("n.test"),
    ];
    expect(topIssues(sites).map((f) => f.host)).toEqual([
      "m.test",
      "a.test",
      "z.test",
    ]);
  });

  it("derives actions only from real state", () => {
    const actions = priorityActions({
      targets: [
        target("new.test", "pending"),
        target("old.test", "expired"),
        target("fresh.test", "verified"),
      ],
      sites: [site("a.test", { open_counts: { critical: 1, high: 2 } })],
      scannedHosts: new Set(["a.test"]),
      scans: [scan("s1", "a.test", "failed")],
      canManage: true,
      canRun: true,
    });
    expect(actions.map((a) => a.id)).toEqual([
      "verify-new.test",
      "reverify-old.test",
      "failed-s1",
      "urgent-a.test",
      "scan-fresh.test",
    ]);
    expect(actions[3]!.label).toContain("3 critical or high findings");
    expect(actions[2]!.href).toBe("#/history?scan=s1");
  });

  it("respects role and skips scan rules when scans did not load", () => {
    const base = {
      targets: [target("new.test", "pending"), target("v.test", "verified")],
      sites: [],
      scannedHosts: null,
    };
    expect(
      priorityActions({
        ...base,
        scans: null,
        canManage: false,
        canRun: false,
      }),
    ).toEqual([]);
    const failed = [scan("s1", "a.test", "failed")];
    expect(
      priorityActions({
        ...base,
        scans: null,
        canManage: false,
        canRun: false,
      }),
    ).toEqual([]);
    expect(
      priorityActions({
        ...base,
        scans: failed,
        canManage: false,
        canRun: false,
      }).map((a) => a.id),
    ).toEqual(["failed-s1"]);
  });

  it("only reports the newest scan of each host as failed", () => {
    const actions = priorityActions({
      targets: [],
      sites: [],
      scannedHosts: null,
      scans: [
        scan("old", "a.test", "failed", "2026-10-10T00:00:00Z"),
        scan("new", "a.test", "completed", "2026-10-18T00:00:00Z"),
      ],
      canManage: true,
      canRun: true,
    });
    expect(actions).toEqual([]);
  });

  it("describes outcomes from the scan record", () => {
    expect(scanOutcome(scan("a", "x.test", "completed"))).toBe(
      "score 70, 3 findings",
    );
    expect(scanOutcome(scan("a", "x.test", "failed"))).toBe("Did not complete");
    expect(scanOutcome(scan("a", "x.test", "cancelled"))).toBe("Cancelled");
    expect(scanOutcome(scan("a", "x.test", "running"))).toBe("In progress");
  });
});

describe("more scanned sites than the overview lists", () => {
  // The server lists at most six sites; h6 to h8 were scanned but are not listed.
  const hosts = Array.from({ length: 9 }, (_, i) => `h${i}.test`);
  const listed = hosts.slice(0, 6).map((h, i) => site(h, { score: 90 - i }));
  const targets = [...hosts, "fresh.test"].map((h) => target(h, "verified"));
  afterEach(() => vi.unstubAllGlobals());

  it("never calls a scanned but unlisted site unscanned", () => {
    const actions = priorityActions({
      targets,
      sites: listed,
      scannedHosts: new Set(hosts),
      scans: [],
      canManage: true,
      canRun: true,
    });
    expect(actions.map((a) => a.id)).toEqual(["scan-fresh.test"]);
    expect(actions[0]!.detail).toBe(
      "Verified, with no completed scan on record.",
    );
  });

  it("makes no unscanned claim at all when the server did not say", () => {
    const actions = priorityActions({
      targets,
      sites: listed,
      scannedHosts: null,
      scans: [],
      canManage: true,
      canRun: true,
    });
    expect(actions.filter((a) => a.id.startsWith("scan-"))).toEqual([]);
  });

  it("classifies each host by what is actually known", () => {
    const known = new Set(hosts);
    expect(scanRecord("h0.test", listed, known)).toBe("listed");
    expect(scanRecord("h7.test", listed, known)).toBe("unlisted");
    expect(scanRecord("fresh.test", listed, known)).toBe("never");
    expect(scanRecord("h7.test", listed, null)).toBe("unknown");
    expect(scanRecord("h0.test", listed, null)).toBe("listed");
  });

  it("says when the score comparison covers only some sites", () => {
    const base: Overview = { sites: listed, fix_first: null, other_open: 0 };
    expect(scoreScope({ ...base, scanned_hosts: hosts })).toBe(
      "Lowest score among the 6 most recently scanned sites (9 scanned)",
    );
    expect(scoreScope({ ...base, scanned_hosts: hosts.slice(0, 6) })).toBe(
      "Lowest-scoring site",
    );
    expect(scoreScope(base)).toBe("Lowest-scoring site listed");
    expect(
      scoreScope({
        ...base,
        sites: listed.slice(0, 1),
        scanned_hosts: ["h0.test"],
      }),
    ).toBe("Your site");
  });

  it("renders unlisted, unscanned and unknown hosts honestly", async () => {
    stubScans(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0 }),
    }));
    const inventory = [
      target("h0.test", "verified"),
      target("h7.test", "verified"),
      target("fresh.test", "verified"),
    ];
    const { rerender } = render(
      <BentoGrid
        overview={{
          sites: listed,
          fix_first: null,
          other_open: 0,
          scanned_hosts: hosts,
        }}
        targets={inventory}
        refreshKey="x"
        canManage
        canRun
        organizationId="org1"
      />,
    );
    await screen.findByText("No scans yet.");
    expect(
      screen.getByText(/Lowest score among the 6 most recently scanned/),
    ).toBeInTheDocument();
    const inv = within(screen.getByRole("region", { name: "Site inventory" }));
    expect(inv.getByText(/score 90, 0 open/)).toBeInTheDocument(); // h0 is listed
    expect(
      inv.getByText(/scanned, not among the sites listed here/),
    ).toBeInTheDocument();
    expect(inv.getByText(/no completed scan on record/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Run a scan of fresh\.test/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Run a scan of h7\.test/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/not scanned yet|never/i),
    ).not.toBeInTheDocument();

    // An older server without the full list: nothing is claimed either way.
    rerender(
      <BentoGrid
        overview={{ sites: listed, fix_first: null, other_open: 0 }}
        targets={inventory}
        refreshKey="x"
        canManage
        canRun
        organizationId="org1"
      />,
    );
    expect(
      within(
        screen.getByRole("region", { name: "Site inventory" }),
      ).getAllByText(/not in this overview/),
    ).toHaveLength(2);
    expect(
      screen.queryByRole("link", { name: /Run a scan of/ }),
    ).not.toBeInTheDocument();
  });

  it("summary notes say when totals cover only the listed sites", () => {
    render(
      <SummaryCards
        overview={{
          sites: listed,
          fix_first: null,
          other_open: 0,
          scanned_hosts: hosts,
        }}
        targets={targets}
      />,
    );
    expect(screen.getByText("9 scanned")).toBeInTheDocument();
    expect(
      screen.getByText("none on the 6 most recently scanned sites"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("of the 6 most recently scanned sites; a heuristic"),
    ).toBeInTheDocument();
  });
});

function stubScans(response: () => Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(response));
}

const emptyOverview: Overview = { sites: [], fix_first: null, other_open: 0 };

describe("BentoGrid states", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows honest empty states and no score when there is no data", async () => {
    stubScans(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0 }),
    }));
    render(
      <BentoGrid
        overview={emptyOverview}
        targets={[]}
        refreshKey="x"
        canManage
        canRun
        organizationId="org1"
      />,
    );
    expect(screen.getByText(/No scored scan yet/)).toBeInTheDocument();
    expect(screen.getByText(/No sites added yet/)).toBeInTheDocument();
    expect(
      screen.getByText(/Reports appear after your first/),
    ).toBeInTheDocument();
    expect(await screen.findByText("No scans yet.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /download/i }),
    ).not.toBeInTheDocument();
  });

  it("shows an error, not stand-in data, when scans cannot be loaded", async () => {
    stubScans(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "boom" }),
    }));
    render(
      <BentoGrid
        overview={emptyOverview}
        targets={[]}
        refreshKey="x"
        canManage
        canRun
        organizationId="org1"
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(
      screen.getByText(/failed scans are not checked here/),
    ).toBeInTheDocument();
    expect(screen.queryByText("No scans yet.")).not.toBeInTheDocument();
  });

  it("links the score, issues, scans and report downloads to real records", async () => {
    stubScans(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        items: [scan("s9", "a.test", "completed")],
        total: 1,
      }),
    }));
    const overview: Overview = {
      sites: [
        site("a.test", {
          score: 62,
          grade: "C",
          top_finding: top("a.test", "high"),
          open_total: 1,
          open_counts: { high: 1 },
        }),
      ],
      fix_first: top("a.test", "high"),
      other_open: 0,
    };
    render(
      <BentoGrid
        overview={overview}
        targets={[target("a.test", "verified")]}
        refreshKey="x"
        canManage
        canRun
        organizationId="org1"
      />,
    );
    expect(
      screen.getByRole("img", {
        name: /Heuristic score 62 out of 100, grade C/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ownership verified")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Finding on a.test/ }),
    ).toHaveAttribute(
      "href",
      "#/findings?scan=scan-a.test&finding=SS-HDR-HSTS-001",
    );
    expect(
      screen.getByRole("button", { name: "Download PDF report for a.test" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: /a.test.*score 70, 3 findings/ }),
    ).toHaveAttribute("href", "#/history?scan=s9");
  });
});
