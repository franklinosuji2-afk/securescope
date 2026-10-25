import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScheduleWarning, {
  scheduleProblem,
} from "../components/ScheduleWarning";
import type { Schedule } from "../types";

const base: Schedule = {
  target_id: "t1",
  hostname: "example.org",
  frequency: "daily",
  url: "https://example.org/",
  notify: true,
  next_run_at: "2026-10-26T10:00:00Z",
  last_run_at: "2026-10-25T10:00:00Z",
  last_scan_id: null,
  last_outcome: "completed, score 90",
  health: "ok",
};

function serve(items: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status: ok ? 200 : 403,
      json: async () => items,
    })),
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("scheduleProblem", () => {
  it("is silent for healthy and switched-off schedules", () => {
    expect(scheduleProblem(base)).toBeNull();
    expect(scheduleProblem({ ...base, health: "off" })).toBeNull();
    expect(scheduleProblem({ ...base, health: undefined })).toBeNull();
  });
  it("explains a late run and a failed run", () => {
    expect(scheduleProblem({ ...base, health: "overdue" })).toMatch(/late/);
    expect(
      scheduleProblem({
        ...base,
        health: "problem",
        last_outcome: "error: the run failed",
      }),
    ).toMatch(/did not complete \(error: the run failed\)/);
  });
});

describe("ScheduleWarning", () => {
  it("names the sites that need attention", async () => {
    serve({
      available: true,
      items: [
        { ...base, health: "overdue" },
        { ...base, target_id: "t2", hostname: "other.org", health: "ok" },
      ],
    });
    render(<ScheduleWarning />);
    expect(await screen.findByTestId("schedule-warning")).toHaveTextContent(
      "A scheduled scan needs attention. example.org.",
    );
    expect(screen.getByTestId("schedule-warning")).not.toHaveTextContent(
      "other.org",
    );
  });
  it("shows nothing when all is well, when the request fails, or when the reply is not a schedule list", async () => {
    for (const reply of [
      { available: true, items: [base] },
      { error: "nope" },
      { sites: [] },
    ]) {
      serve(reply);
      const { container, unmount } = render(<ScheduleWarning />);
      await new Promise((r) => setTimeout(r, 20));
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new Error("x"))),
    );
    const { container } = render(<ScheduleWarning />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
