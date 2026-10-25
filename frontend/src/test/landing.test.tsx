import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
