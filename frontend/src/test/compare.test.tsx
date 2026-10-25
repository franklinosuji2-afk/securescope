import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Compare from "../pages/Compare";
import type { Finding, ScanComparison, ScanSummary } from "../types";

vi.mock("../api", () => ({
  getScan: vi.fn(),
  listScans: vi.fn(),
  compareScans: vi.fn(),
}));
import * as api from "../api";

const finding = (id: string, title: string): Finding =>
  ({
    id,
    title,
    severity: "low",
    category: "headers",
    description: "d",
    remediation: "r",
    fingerprint: `fp-${id}`,
    confidence: "high",
    references: [],
  }) as unknown as Finding;

const summary = (id: string, at: string): ScanSummary =>
  ({
    id,
    host: "a.example",
    status: "completed",
    score: 90,
    created_at: at,
  }) as unknown as ScanSummary;

function comparison(extra: Partial<ScanComparison>): ScanComparison {
  return {
    host: "a.example",
    older: {
      id: "s1",
      scanned_at: "2026-10-01T10:00:00Z",
      status: "completed",
      score: 90,
      grade: "A",
    },
    newer: {
      id: "s2",
      scanned_at: "2026-10-02T10:00:00Z",
      status: "completed",
      score: 90,
      grade: "A",
    },
    score_change: 0,
    new_findings: [],
    resolved_findings: [],
    unchanged_findings: [],
    note: "n",
    ...extra,
  } as ScanComparison;
}

function show(result: ScanComparison) {
  vi.mocked(api.getScan).mockResolvedValue(
    summary("s2", "2026-10-02T10:00:00Z") as never,
  );
  vi.mocked(api.listScans).mockResolvedValue({
    items: [summary("s1", "2026-10-01T10:00:00Z")],
    total: 1,
  } as never);
  vi.mocked(api.compareScans).mockResolvedValue(result);
  render(
    <Compare
      route={{ page: "compare", scanId: "s2", compareWith: null } as never}
    />,
  );
}

describe("comparing two scans", () => {
  beforeEach(() => vi.resetAllMocks());

  it("keeps findings of a check that did not run out of new and resolved", async () => {
    show(
      comparison({
        not_comparable_findings: [finding("SS-CORS-001", "CORS problem")],
        not_comparable_checks: ["No risky cross-origin (CORS) headers"],
      }),
    );
    const group = await screen.findByRole("region", {
      name: "Cannot be compared",
    });
    expect(within(group).getByText("CORS problem")).toBeInTheDocument();
    expect(screen.getByText(/did not run in the other/)).toBeInTheDocument();
    expect(screen.getByText(/No risky cross-origin/)).toBeInTheDocument();
  });

  it("shows no such group when every check ran in both scans", async () => {
    show(
      comparison({ not_comparable_findings: [], not_comparable_checks: [] }),
    );
    await screen.findByRole("region", { name: "Still present" });
    expect(
      screen.queryByRole("region", { name: "Cannot be compared" }),
    ).toBeNull();
  });
});
