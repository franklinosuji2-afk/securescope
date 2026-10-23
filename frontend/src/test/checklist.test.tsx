import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Checklist from "../components/Checklist";
import type { Finding, ScanDetail } from "../types";

const finding = (id: string, severity: Finding["severity"]): Finding =>
  ({
    id,
    title: id,
    severity,
    category: "x",
    description: "",
    evidence: null,
    remediation: "",
    confidence: "high",
    fingerprint: null,
    status: "open",
    status_note: null,
    first_seen_at: null,
    last_seen_at: null,
  }) as Finding;

function scan(checks: string[], findings: Finding[]): ScanDetail {
  return {
    id: "s1",
    target_url: "https://example.org/",
    host: "example.org",
    status: "completed",
    score: 100,
    grade: "A",
    created_at: "2026-10-22T10:00:00Z",
    finished_at: "2026-10-22T10:00:05Z",
    counts: {},
    error: null,
    metadata: { checks_run: checks, checks_skipped: [] },
    findings,
    score_note: "",
  } as unknown as ScanDetail;
}

describe("the checklist", () => {
  it("names the wider checks in words", () => {
    render(
      <Checklist
        scan={scan(["mixed-content", "sri", "cors", "email-spf"], [])}
      />,
    );
    expect(
      screen.getByText(/The page loads nothing over plain HTTP/),
    ).toBeTruthy();
    expect(
      screen.getByText(/An SPF record limits who can send mail/),
    ).toBeTruthy();
    expect(screen.getAllByText("✓ Passed")).toHaveLength(4);
  });

  it("does not tick a check that raised a note meaning not done yet", () => {
    render(
      <Checklist
        scan={scan(
          ["dns-caa", "dnssec", "email-dmarc", "robots-sitemap", "cors"],
          [
            finding("SS-DNS-CAA-001", "info"),
            finding("SS-DNS-DNSSEC-001", "info"),
            finding("SS-DNS-DMARC-002", "info"),
            finding("SS-DISC-ROBOTS-001", "info"),
          ],
        )}
      />,
    );
    expect(screen.getAllByText("✕ Needs attention")).toHaveLength(4);
    expect(screen.getAllByText("✓ Passed")).toHaveLength(1);
  });
});
