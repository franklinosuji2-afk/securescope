import { describe, expect, it } from "vitest";
import { deltaText, fixFirst, openCounts, setupSteps, siteSummaries } from "../overview";
import type { Finding, ScanDetail, ScanSummary, Severity, Target } from "../types";

function target(hostname: string, status: Target["status"] = "pending"): Target {
  return {
    id: hostname,
    hostname,
    status,
    challenge_token: "t".repeat(20),
    challenge_expires_at: "2026-10-20T00:00:00Z",
    verified_at: status === "verified" ? "2026-10-18T10:00:00Z" : null,
    verification_method: status === "verified" ? "dns_txt" : null,
    last_check_at: null,
    last_check_error: null,
    created_at: "2026-10-18T09:00:00Z",
    dns_record_name: "",
    dns_record_value: "",
    http_file_url: "",
    http_file_content: "",
  };
}

function summary(id: string, host: string, created: string, score: number | null, status: ScanSummary["status"] = "completed"): ScanSummary {
  return { id, target_url: `https://${host}/`, host, status, score, grade: "A", created_at: created, finished_at: created, counts: {} };
}

function finding(id: string, severity: Severity, status: Finding["status"] = "open", confidence: Finding["confidence"] = "high"): Finding {
  return {
    id, title: id, severity, category: "c", description: "d", evidence: null, remediation: "r", confidence,
    fingerprint: id.padEnd(32, "x"), status, status_note: null, first_seen_at: null, last_seen_at: null,
  };
}

function detail(base: ScanSummary, findings: Finding[]): ScanDetail {
  return { ...base, error: null, metadata: null, findings, score_note: "" };
}

describe("setupSteps", () => {
  it("starts with adding a site when there is nothing yet", () => {
    const steps = setupSteps([], [], true);
    expect(steps.map((s) => s.state)).toEqual(["current", "waiting", "waiting", "waiting"]);
    expect(steps[0]!.action?.href).toBe("#/targets");
  });

  it("moves to verification once a site is added, naming the site", () => {
    const steps = setupSteps([target("example.org")], [], true);
    expect(steps.map((s) => s.state)).toEqual(["done", "current", "waiting", "waiting"]);
    expect(steps[1]!.action?.label).toBe("Verify example.org");
    expect(steps[1]!.detail).toContain("example.org");
  });

  it("moves to scanning once a site is verified, with no button because the form is on the page", () => {
    const steps = setupSteps([target("example.org", "verified")], [], true);
    expect(steps.map((s) => s.state)).toEqual(["done", "done", "current", "waiting"]);
    expect(steps[2]!.action).toBeNull();
  });

  it("offers no buttons to roles that cannot manage targets", () => {
    const steps = setupSteps([], [], false);
    expect(steps.every((s) => s.action === null)).toBe(true);
  });
});

describe("siteSummaries", () => {
  const targets = [target("a.example", "verified")];

  it("uses completed scans only and compares with the previous scan of the same host", () => {
    const scans = [
      summary("s3", "a.example", "2026-10-18T12:00:00Z", 100),
      summary("s2", "a.example", "2026-10-18T11:00:00Z", 96),
      summary("s1", "a.example", "2026-10-18T10:00:00Z", 80),
      summary("s4", "a.example", "2026-10-18T13:00:00Z", null, "failed"),
    ];
    const [site] = siteSummaries(targets, scans);
    expect(site!.latest.id).toBe("s3");
    expect(site!.previous!.id).toBe("s2");
    expect(site!.delta).toBe(4);
    expect(site!.verified).toBe(true);
  });

  it("reports no delta for a first scan and keeps hosts apart", () => {
    const sites = siteSummaries(targets, [
      summary("x", "a.example", "2026-10-18T10:00:00Z", 90),
      summary("y", "b.example", "2026-10-18T11:00:00Z", 70),
    ]);
    expect(sites.map((s) => s.host)).toEqual(["b.example", "a.example"]);
    expect(sites.every((s) => s.delta === null)).toBe(true);
    expect(sites.find((s) => s.host === "b.example")!.verified).toBe(false);
  });

  it("describes changes in words, not colour", () => {
    expect(deltaText(null)).toBe("First scan of this site");
    expect(deltaText(0)).toBe("No change since the previous scan");
    expect(deltaText(4)).toBe("▲ Up 4 since the previous scan");
    expect(deltaText(-7)).toBe("▼ Down 7 since the previous scan");
  });
});

describe("fixFirst", () => {
  const base = summary("s1", "a.example", "2026-10-18T10:00:00Z", 80);

  it("picks the most severe open finding and counts the rest", () => {
    const fix = fixFirst([detail(base, [finding("LOW-1", "low"), finding("HIGH-1", "high"), finding("INFO-1", "info")])]);
    expect(fix!.finding.id).toBe("HIGH-1");
    expect(fix!.others).toBe(2);
  });

  it("ignores resolved, accepted and false-positive findings", () => {
    const fix = fixFirst([
      detail(base, [
        finding("HIGH-1", "high", "resolved"),
        finding("HIGH-2", "high", "accepted_risk"),
        finding("HIGH-3", "high", "false_positive"),
        finding("LOW-1", "low"),
      ]),
    ]);
    expect(fix!.finding.id).toBe("LOW-1");
    expect(fix!.others).toBe(0);
  });

  it("prefers a confirmed finding over a heuristic one of the same severity", () => {
    const fix = fixFirst([detail(base, [finding("A-HEUR", "medium", "open", "medium"), finding("B-SURE", "medium")])]);
    expect(fix!.finding.id).toBe("B-SURE");
  });

  it("returns null when nothing is open", () => {
    expect(fixFirst([detail(base, [finding("X", "high", "resolved")])])).toBeNull();
    expect(fixFirst([])).toBeNull();
  });

  it("counts only open findings by severity", () => {
    expect(openCounts([finding("A", "high"), finding("B", "high"), finding("C", "low", "resolved")])).toEqual({ high: 2 });
  });
});
