import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import securityTxt from "../../public/.well-known/security.txt?raw";
import { CONTACT, mailto } from "../contact";
import LegalPage from "../pages/Legal";
import { AuthProvider } from "../auth";

const sources = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("public contact addresses", () => {
  it("are all on the product domain", () => {
    for (const address of Object.values(CONTACT))
      expect(address).toMatch(/^[a-z]+@getsecurescope\.com$/);
    expect(Object.keys(CONTACT).sort()).toEqual([
      "general",
      "privacy",
      "security",
      "support",
    ]);
  });

  it("build mailto links", () => {
    expect(mailto("security")).toBe("mailto:security@getsecurescope.com");
  });

  it("security.txt points at the same security address", () => {
    expect(securityTxt).toContain(`Contact: ${mailto("security")}`);
  });

  it("no personal mailbox is written into the application source", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10);
    const offenders = Object.entries(sources)
      .filter(([file]) => !file.includes("/test/"))
      .filter(([, text]) => /@(gmx\.|gmail\.|googlemail\.)/i.test(text))
      .map(([file]) => file);
    expect(offenders).toEqual([]);
  });

  it("no secret-looking value is bundled into the frontend", () => {
    const offenders = Object.entries(sources)
      .filter(([file]) => !file.includes("/test/"))
      .filter(([, text]) =>
        /(api[-_]?key|xkeysib|re_[A-Za-z0-9]{16,})/i.test(text),
      )
      .map(([file]) => file);
    expect(offenders).toEqual([]);
  });
});

describe("legal pages use the product addresses", () => {
  it("the Impressum lists general, support, privacy and security", () => {
    render(
      <AuthProvider>
        <LegalPage page="impressum" />
      </AuthProvider>,
    );
    for (const address of Object.values(CONTACT)) {
      const link = screen.getByRole("link", { name: address });
      expect(link).toHaveAttribute("href", `mailto:${address}`);
    }
  });

  it("the privacy notice names the privacy address", () => {
    render(
      <AuthProvider>
        <LegalPage page="privacy" />
      </AuthProvider>,
    );
    expect(screen.getByRole("link", { name: CONTACT.privacy })).toHaveAttribute(
      "href",
      `mailto:${CONTACT.privacy}`,
    );
  });

  it("the Impressum shows a real postal address, not a placeholder", () => {
    const { container } = render(
      <AuthProvider>
        <LegalPage page="impressum" />
      </AuthProvider>,
    );
    const text = container.textContent ?? "";
    expect(text).toContain("Mariendorfer Weg 52");
    expect(text).toContain("12051 Berlin");
    expect(text).not.toMatch(/\[[^\]]*to be added[^\]]*\]/i);
  });
});
