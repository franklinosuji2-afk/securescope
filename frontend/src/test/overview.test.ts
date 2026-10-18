import { describe, expect, it } from "vitest";
import {
  chartPoints,
  deltaText,
  historySummary,
  setupSteps,
} from "../overview";
import type { Target } from "../types";

function target(
  hostname: string,
  status: Target["status"] = "pending",
): Target {
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

describe("setupSteps", () => {
  it("starts with adding a site when there is nothing yet", () => {
    const steps = setupSteps([], false, true);
    expect(steps.map((s) => s.state)).toEqual([
      "current",
      "waiting",
      "waiting",
      "waiting",
    ]);
    expect(steps[0]!.action?.href).toBe("#/targets");
  });

  it("moves to verification once a site is added, naming the site", () => {
    const steps = setupSteps([target("example.org")], false, true);
    expect(steps.map((s) => s.state)).toEqual([
      "done",
      "current",
      "waiting",
      "waiting",
    ]);
    expect(steps[1]!.action?.label).toBe("Verify example.org");
    expect(steps[1]!.detail).toContain("example.org");
  });

  it("moves to scanning once a site is verified, with no button because the form is on the page", () => {
    const steps = setupSteps([target("example.org", "verified")], false, true);
    expect(steps.map((s) => s.state)).toEqual([
      "done",
      "done",
      "current",
      "waiting",
    ]);
    expect(steps[2]!.action).toBeNull();
  });

  it("offers no buttons to roles that cannot manage targets", () => {
    expect(setupSteps([], false, false).every((s) => s.action === null)).toBe(
      true,
    );
  });
});

describe("score change wording", () => {
  it("describes changes in words, not colour", () => {
    expect(deltaText(null)).toBe("First scan of this site");
    expect(deltaText(0)).toBe("No change since the previous scan");
    expect(deltaText(4)).toBe("▲ Up 4 since the previous scan");
    expect(deltaText(-7)).toBe("▼ Down 7 since the previous scan");
  });
});

describe("score history chart", () => {
  it("plots on a fixed 0-100 scale, so a drop always looks like a drop", () => {
    const [a, b] = chartPoints([100, 0], 100, 50, 0);
    expect(a).toEqual({ x: 0, y: 0 });
    expect(b).toEqual({ x: 100, y: 50 });
    const [low, high] = chartPoints([40, 60], 100, 100, 0);
    expect(low!.y).toBeGreaterThan(high!.y); // higher score is higher on the chart
  });

  it("clamps out-of-range scores and centres a single point", () => {
    expect(chartPoints([150], 100, 50, 0)[0]).toEqual({ x: 50, y: 0 });
    expect(chartPoints([-5], 100, 50, 0)[0]!.y).toBe(50);
  });

  it("gives the same information as text", () => {
    expect(historySummary([])).toBe("No score history yet.");
    expect(historySummary([90])).toBe("One scan so far, score 90.");
    expect(historySummary([76, 84, 100])).toBe(
      "Score history over 3 scans: 76, 84, 100. Now 100, up from 76.",
    );
    expect(historySummary([100, 90])).toBe(
      "Score history over 2 scans: 100, 90. Now 90, down from 100.",
    );
    expect(historySummary([80, 85, 80])).toContain("unchanged from 80");
  });
});
