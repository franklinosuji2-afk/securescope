import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import TimeChart, { smoothPath } from "../components/TimeChart";
import { Donut, Levels } from "../components/viz";

const series = [
  { date: "2026-10-26", visitors: 10, views: 20 },
  { date: "2026-10-27", visitors: 15, views: 33 },
  { date: "2026-10-28", visitors: 12, views: 25 },
];
const previous = [
  { date: "2026-10-19", visitors: 20, views: 40 },
  { date: "2026-10-20", visitors: 10, views: 30 },
  { date: "2026-10-21", visitors: 12, views: 25 },
];

describe("smoothPath", () => {
  it("returns an empty path for no points and a move for one", () => {
    expect(smoothPath([])).toBe("");
    expect(smoothPath([[4, 5]])).toBe("M4,5");
  });
  it("never overshoots a flat run", () => {
    const d = smoothPath([
      [0, 10],
      [10, 10],
      [20, 10],
    ]);
    // Path numbers alternate x, y; only the y values matter here.
    const nums = [...d.matchAll(/-?\d+(?:\.\d+)?/g)].map((m) => Number(m[0]));
    const ys = nums.filter((_, i) => i % 2 === 1);
    expect(Math.max(...ys)).toBeLessThanOrEqual(10);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(10);
  });
});

describe("TimeChart", () => {
  const plot = () =>
    screen.getByRole("group", { name: /Use the left and right/ });

  it("shows exact numbers and the change against the previous period", () => {
    render(<TimeChart series={series} previous={previous} label="chart" />);
    plot().focus();
    fireEvent.keyDown(plot(), { key: "ArrowRight" });
    fireEvent.keyDown(plot(), { key: "ArrowRight" });
    expect(screen.getByText("Tue, Oct 27")).toBeInTheDocument();
    expect(screen.getByText(/\+50% vs 10/)).toBeInTheDocument();
    fireEvent.keyDown(plot(), { key: "Escape" });
    expect(screen.queryByText("Tue, Oct 27")).not.toBeInTheDocument();
  });

  it("switches lines off from the legend", async () => {
    const { container } = render(
      <TimeChart series={series} previous={previous} label="chart" />,
    );
    const views = screen.getByRole("button", { name: /Page views/ });
    expect(views).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(views);
    expect(views).toHaveAttribute("aria-pressed", "false");
    fireEvent.keyDown(plot(), { key: "End" });
    const tip = container.querySelector<HTMLElement>(".tc-tip");
    expect(tip).not.toBeNull();
    expect(within(tip!).queryByText("Page views")).not.toBeInTheDocument();
    expect(within(tip!).getByText("Visitors")).toBeInTheDocument();
  });

  it("omits the previous-period key when there is no earlier data", () => {
    render(<TimeChart series={series} previous={null} label="chart" />);
    expect(
      screen.queryByRole("button", { name: "Previous period" }),
    ).not.toBeInTheDocument();
  });
});

describe("Donut and Levels", () => {
  it("repeats every count and share in the legend", () => {
    render(
      <Donut
        label="Scans by outcome"
        total={4}
        unit="scans"
        parts={[
          { label: "Completed", value: 3, tone: "good" },
          { label: "Error", value: 1, tone: "bad" },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Scans by outcome" })).toBeTruthy();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
  it("handles an all-zero donut without NaN", () => {
    render(
      <Donut
        label="empty"
        total={0}
        unit="scans"
        parts={[{ label: "Completed", value: 0, tone: "good" }]}
      />,
    );
    expect(screen.getByText("–")).toBeInTheDocument();
  });
  it("lists each percentile with its value", () => {
    render(
      <Levels
        label="Latency"
        unit="ms"
        levels={[
          { label: "Median", value: 38 },
          { label: "p99", value: 1210 },
        ]}
      />,
    );
    expect(screen.getByText("1210 ms")).toBeInTheDocument();
  });
});
