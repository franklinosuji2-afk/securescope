import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CONTACT } from "../contact";
import Landing from "../pages/Landing";

function page(): { text: string; container: HTMLElement } {
  const { container } = render(<Landing />);
  return { text: container.textContent ?? "", container };
}

describe("public home page", () => {
  it("links to security reporting from the footer and shows the support address only once, on the Impressum", () => {
    const { container } = page();
    const mail = container.querySelector(`a[href="mailto:${CONTACT.support}"]`);
    expect(mail).toBeNull();
    expect(container.textContent).not.toContain(CONTACT.support);
    expect(container.querySelector('a[href="#/impressum"]')).not.toBeNull();
    expect(
      container.querySelector('a[href="/.well-known/security.txt"]'),
    ).not.toBeNull();
  });

  it("answers who it is for and what scheduled monitoring does", () => {
    const { text } = page();
    expect(text).toContain("Who is SecureScope for?");
    expect(text).toContain("What does scheduled monitoring do?");
  });

  it("says scheduled monitoring is not on sale yet", () => {
    const { text } = page();
    expect(text).toMatch(/Coming soon/);
  });

  it("makes none of the claims a basic external check cannot support", () => {
    const { text } = page();
    const forbidden = [
      /guarantee/i,
      /completely secure/i,
      /fully secure/i,
      /100% secure/i,
      /unhackable/i,
      /bank-grade/i,
      /military-grade/i,
      /penetration test(?:ing)? (?:service|included)/i,
      /\bcertified\b/i,
      /trusted by/i,
      /\b\d[\d,.]*\+? (?:customers|companies|teams|users)\b/i,
      /testimonial/i,
    ];
    for (const pattern of forbidden) expect(text).not.toMatch(pattern);
  });
});

describe("two products on the home page", () => {
  it("names both products and gives App Scanning an honest status", () => {
    const { container } = page();
    const text = container.textContent ?? "";
    expect(text).toContain("Website Scanning");
    expect(text).toContain("App Scanning");
    expect(container.querySelector("#app-scanning")?.textContent).toContain(
      "In development",
    );
    expect(container.querySelector("#products")?.textContent).toContain(
      "Available",
    );
  });

  it("does not present planned features as available", () => {
    const { container } = page();
    const card = container.querySelector("#products")?.textContent ?? "";
    const planned = card.slice(card.indexOf("Planned, not available"));
    for (const item of ["SAST", "Secret detection", "vulnerability database"])
      expect(planned).toContain(item);
    // Nothing outside that list claims them as working.
    const rest = card.slice(0, card.indexOf("Planned, not available"));
    expect(rest).not.toMatch(/SAST|Secret detection/);
  });

  it("says an unavailable source is never a clean result", () => {
    const { container } = page();
    const section = container.querySelector("#app-scanning")?.textContent ?? "";
    expect(section).toMatch(/never reported as clean/);
    expect(section).toMatch(/not a penetration test/);
    expect(section).toContain("Illustrative example");
  });

  it("publishes no App Scanning allowances, prices or unlimited claims", () => {
    const { container } = page();
    const section = container.querySelector("#app-scanning")?.textContent ?? "";
    const products = container.querySelector("#products")?.textContent ?? "";
    for (const t of [section, products]) {
      expect(t).not.toMatch(/unlimited/i);
      expect(t).not.toMatch(/\d+ runs|runs per month|€|\$\s?\d/i);
    }
  });

  it("makes no request to the App Scanning API", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    page();
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("links to the privacy notice and the terms from the trust section", () => {
    const { container } = page();
    const trust = container.querySelector("#app-scanning");
    expect(trust?.querySelector('a[href="#/privacy"]')).not.toBeNull();
    expect(trust?.querySelector('a[href="#/terms"]')).not.toBeNull();
  });
});
