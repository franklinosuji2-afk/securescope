import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../auth";
import LegalPage from "../pages/Legal";

function text(page: "privacy" | "terms" | "impressum"): string {
  const { container } = render(
    <AuthProvider>
      <LegalPage page={page} />
    </AuthProvider>,
  );
  return container.textContent ?? "";
}

describe("legal text matches what the app does", () => {
  it("the privacy notice names the pages that are really counted", () => {
    const t = text("privacy");
    for (const page of ["home page", "sample report", "Agency features page"])
      expect(t).toContain(page);
  });

  it("the privacy notice lists every item kept in the browser", () => {
    const t = text("privacy");
    for (const key of [
      "ss_session",
      "ss_csrf",
      "ss_oauth",
      "securescope-theme",
      "securescope.org",
      "securescope.invite",
    ])
      expect(t).toContain(key);
  });

  it("does not call Google or GitHub processors, and does not claim the audit log holds IP addresses", () => {
    const t = text("privacy");
    expect(t).toContain("are not our processors");
    expect(t).toContain("contains no IP addresses");
  });

  it("says deleted data can remain briefly in backups", () => {
    expect(text("privacy")).toContain("restore history");
  });

  it("the terms do not treat verification as proof of permission", () => {
    expect(text("terms")).toContain("technical control only");
  });
});

describe("pre-launch: no unconfirmed business, tax or hosting claims", () => {
  it("the Impressum invents no register, VAT or company data", () => {
    const t = text("impressum");
    expect(t).toContain("not a registered company");
    for (const word of [
      "Handelsregister",
      "HRB",
      "USt-IdNr",
      "Kleinunternehmer",
      "GmbH",
    ])
      expect(t).not.toContain(word);
    expect(t).not.toContain("No VAT identification number");
  });

  it("the privacy notice does not promise that everything is hosted in the EU", () => {
    const t = text("privacy");
    expect(t).not.toMatch(
      /all (your )?data (is|are) (stored|hosted|processed) in the (EU|European)/i,
    );
    expect(t).not.toMatch(/Render[^.]*(Frankfurt|Germany|EU)/);
    // Verified in the Render dashboard on 24 October 2026: the API service runs in Oregon.
    expect(t).toContain("United States, Oregon");
  });

  it("the terms say the service is in development and promise no payment terms", () => {
    const t = text("terms");
    expect(t).toContain("still in development");
    expect(t).not.toContain("early access");
  });
});
