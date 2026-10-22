import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanComparison from "../components/PlanComparison";

describe("the plan comparison", () => {
  it("lists webhook alerts for Professional and Agency, not Free", () => {
    render(<PlanComparison />);
    const row = screen
      .getByText("Signed webhook alerts to up to 3 HTTPS addresses")
      .closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement).getAllByRole("cell");
    expect(cells.map((c) => c.textContent)).toEqual([
      "–Not included",
      "✓Included",
      "✓Included",
    ]);
  });

  it("no longer lists webhooks as planned", () => {
    render(<PlanComparison />);
    expect(screen.queryByText(/API and webhooks/)).toBeNull();
    expect(screen.getByText(/A public API/)).toBeTruthy();
  });
});
