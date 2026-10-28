import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HomeHero, HomeProducts } from "../components/HomeHero";

function hero() {
  return render(<HomeHero register="#/register" onApp={() => undefined} />);
}

describe("home hero", () => {
  it("opens on the missing header with its evidence and a fix", () => {
    hero();
    expect(
      screen.getByText("Content-Security-Policy header is missing"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "content-security-policy-report-only: default-src 'self'",
      ),
    ).toBeInTheDocument();
  });

  it("says the example is not a real scan", () => {
    const { container } = hero();
    expect(container.textContent).toContain(
      "Illustrative example, not a real scan",
    );
  });

  it("shows another finding when a marked line is chosen", () => {
    hero();
    fireEvent.click(
      screen.getByRole("button", {
        name: /strict-transport-security: max-age=86400/,
      }),
    );
    expect(
      screen.getByText("Strict-Transport-Security max-age is short"),
    ).toBeInTheDocument();
  });

  it("switches to the dependency file and never presents it as available or clean", () => {
    const { container } = hero();
    fireEvent.click(screen.getByRole("tab", { name: "package.json" }));
    expect(screen.getByRole("tab", { name: "package.json" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const text = container.textContent ?? "";
    expect(text).toContain("In development");
    expect(text).toContain("never shown as clean");
    expect(text).toContain("Not checked: the version is a range");
  });

  it("keeps the call to action and the sample report link", () => {
    hero();
    expect(
      screen.getByRole("link", { name: "Scan your website" }),
    ).toHaveAttribute("href", "#/register");
    expect(
      screen.getByRole("link", { name: "View sample report" }),
    ).toHaveAttribute("href", "#/sample-report");
  });
});

describe("home products", () => {
  it("marks Website Scanning available and App Scanning in development, with planned work listed apart", () => {
    const { container } = render(
      <HomeProducts
        register="#/register"
        onApp={() => undefined}
        planned={["Code analysis (SAST)"]}
        works={["Reading supported dependency manifests"]}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Available");
    expect(text).toContain("In development");
    const before = text.slice(0, text.indexOf("Planned, not available"));
    expect(before).not.toMatch(/SAST|Secret detection/);
    expect(text).toContain("Code analysis (SAST)");
  });
});
