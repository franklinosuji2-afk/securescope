import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CONTACT } from "../contact";
import Landing from "../pages/Landing";

function page(): { text: string; container: HTMLElement } {
  const { container } = render(<Landing />);
  return { text: container.textContent ?? "", container };
}

afterEach(() => {
  window.location.hash = "";
});

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

  it("has the four blocks and one primary action", () => {
    const { container } = page();
    const headings = [...container.querySelectorAll("main h1, main h2")].map(
      (h) => h.textContent,
    );
    expect(headings).toEqual([
      "Find the security gaps on your website, and know how to fix them.",
      "Two products, with clear status.",
      "Built for people who ship, not security teams.",
      "Three steps, a few minutes.",
    ]);
    const primary = [...container.querySelectorAll("main a.btn")];
    expect(primary.length).toBeGreaterThan(0);
    for (const a of primary) {
      expect(a.textContent).toBe("Scan your website");
      expect(a.getAttribute("href")).toBe("#/register");
    }
  });

  it("keeps the detail off the home page and points to the pages that hold it", () => {
    const { container, text } = page();
    for (const jargon of ["HSTS", "Content-Security-Policy", "DMARC", "CORS"])
      expect(text).not.toContain(jargon);
    expect(text).not.toContain("€");
    expect(container.querySelector("details")).toBeNull();
    for (const href of [
      "#/checks",
      "#/pricing",
      "#/help",
      "#/sample-report",
      "#/early-access",
      "#/agency-features",
    ])
      expect(container.querySelector(`a[href="${href}"]`)).not.toBeNull();
  });

  it("names both products, with App Scanning labelled Early Access and not as available", () => {
    const { container } = page();
    const cards = [...container.querySelectorAll("#products article")];
    expect(cards).toHaveLength(2);
    const [website, app] = cards.map((c) => c.textContent ?? "");
    expect(website).toContain("Website Scanning");
    expect(website).toContain("Available now");
    expect(app).toContain("App Scanning");
    expect(app).toContain("Early Access");
    expect(app).not.toContain("Available now");
    expect(app).toMatch(/not open to everyone yet/);
    expect(app).not.toMatch(/vulnerabilit|scans? your (code|dependencies)/i);
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

  it("makes no request to the App Scanning API", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    page();
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("old section links", () => {
  it.each([
    ["pricing", "#/pricing"],
    ["checks", "#/checks"],
    ["how", "#/checks"],
    ["problem", "#/checks"],
    ["app-scanning", "#/early-access"],
    ["products", "#/early-access"],
  ])("sends #/?section=%s to %s", (section, target) => {
    window.location.hash = `#/?section=${section}`;
    page();
    expect(window.location.hash).toBe(target);
  });

  it("leaves an unknown section alone", () => {
    window.location.hash = "#/?section=nothing";
    page();
    expect(window.location.hash).toBe("#/?section=nothing");
  });
});
