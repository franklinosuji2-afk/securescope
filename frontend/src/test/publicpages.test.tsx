import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import Checks from "../pages/Checks";
import EarlyAccess from "../pages/EarlyAccess";
import Help from "../pages/Help";
import Pricing from "../pages/Pricing";
import {
  APP_PLANNED,
  APP_STEPS,
  APP_WORKS,
  BENEFITS,
  CHECKS,
  CHECK_PLAIN,
  FAQ_GROUPS,
  FEATURES,
  NUMBERS,
  PROBLEMS,
  STEPS,
} from "../publicContent";
import { titleFor } from "../pageTitle";
import { PUBLIC_PAGES, parseHash } from "../router";

function text(ui: ReactElement): { container: HTMLElement; text: string } {
  const { container } = render(ui);
  return { container, text: container.textContent ?? "" };
}

describe("What we check", () => {
  it("keeps every check, with a plain question before the technical detail", () => {
    const { text: t } = text(<Checks />);
    expect(CHECKS).toHaveLength(9);
    for (const c of CHECKS) {
      const plain = CHECK_PLAIN[c.title];
      expect(plain).toBeTruthy();
      expect(t).toContain(c.title);
      expect(t).toContain(c.text);
      expect(t).toContain(plain!);
      expect(t.indexOf(plain!)).toBeLessThan(t.indexOf(c.text));
    }
  });

  it("keeps the steps, features, reasons, numbers and benefits that left the home page", () => {
    const { text: t } = text(<Checks />);
    const items: { title: string; text: string }[] = [
      ...STEPS,
      ...FEATURES,
      ...PROBLEMS,
      ...BENEFITS,
    ];
    for (const item of items) {
      expect(t).toContain(item.title);
      expect(t).toContain(item.text);
    }
    for (const n of NUMBERS) expect(t).toContain(n.label);
    expect(t).toContain("They are not usage statistics or customer results.");
  });

  it("keeps the example finding, and the sample report downloads", () => {
    const { container, text: t } = text(<Checks />);
    expect(t).toContain("Illustrative example, not a real scan");
    expect(
      container.querySelector('a[href="/sample-report.pdf"][download]'),
    ).not.toBeNull();
    expect(container.querySelector('a[href="#/sample-report"]')).not.toBeNull();
  });

  it("has one h1 and links that never use a bare fragment", () => {
    const { container } = text(<Checks />);
    expect(container.querySelectorAll("h1")).toHaveLength(1);
    for (const a of container.querySelectorAll("a[href^='#']:not(.skip-link)"))
      expect(a.getAttribute("href")).toMatch(/^#\//);
  });
});

describe("Pricing", () => {
  it("keeps all three plans, says the paid ones are not on sale and keeps the comparison", () => {
    const { container, text: t } = text(<Pricing />);
    for (const s of [
      "Free",
      "Available now",
      "Professional",
      "Agency",
      "€19",
      "€49",
      "Coming soon",
      "Not on sale yet.",
      "What each plan includes",
      "Prices are planned and may change before launch.",
    ])
      expect(t).toContain(s);
    expect(container.querySelectorAll("h1")).toHaveLength(1);
  });

  it("scrolls to the comparison without changing the route", () => {
    const { container } = text(<Pricing />);
    const scroll = vi.fn();
    const target = container.querySelector("#h-compare") as HTMLElement;
    target.scrollIntoView = scroll;
    window.location.hash = "#/pricing";
    fireEvent.click(screen.getByRole("button", { name: "Compare plans" }));
    expect(scroll).toHaveBeenCalled();
    expect(window.location.hash).toBe("#/pricing");
  });

  it("has no bare fragment links", () => {
    const { container } = text(<Pricing />);
    for (const a of container.querySelectorAll("a[href^='#']:not(.skip-link)"))
      expect(a.getAttribute("href")).toMatch(/^#\//);
  });
});

describe("Help", () => {
  it("keeps every question and answer in three groups", () => {
    const { container, text: t } = text(<Help />);
    const groups = container.querySelectorAll(".faq-group");
    expect([...groups].map((g) => g.querySelector("h2")?.textContent)).toEqual([
      "About SecureScope",
      "Safety and permission",
      "Monitoring and your data",
    ]);
    expect(container.querySelectorAll(".faq-group summary")).toHaveLength(7);
    for (const g of FAQ_GROUPS)
      for (const f of g.items) {
        expect(t).toContain(f.q);
        expect(t).toContain(f.a);
      }
    expect(t).toContain("Who is SecureScope for?");
    expect(t).toContain("What does scheduled monitoring do?");
  });

  it("says App Scanning is in Early Access and cannot report vulnerabilities today", () => {
    const { text: t } = text(<Help />);
    expect(t).toMatch(/in Early Access/);
    expect(t).toMatch(/cannot report vulnerabilities today/);
  });

  it("points to the contact and security pages", () => {
    const { container } = text(<Help />);
    for (const href of [
      "#/impressum",
      "#/privacy",
      "/.well-known/security.txt",
      "#/checks",
    ])
      expect(container.querySelector(`a[href="${href}"]`)).not.toBeNull();
  });
});

describe("App Scanning Early Access", () => {
  it("is labelled Early Access and In development, and is not presented as available", () => {
    const { container } = text(<EarlyAccess />);
    const section = container.querySelector("#app-scanning")?.textContent ?? "";
    expect(section).toContain("Early Access");
    expect(section).toContain("In development");
    expect(section).toMatch(/not generally available/);
    const products = container.querySelector("#products")?.textContent ?? "";
    expect(products).toContain("Available");
    expect(products).toContain("Early Access");
  });

  it("does not present planned features as available", () => {
    const { container } = text(<EarlyAccess />);
    const card = container.querySelector("#products")?.textContent ?? "";
    const planned = card.slice(card.indexOf("Planned, not available"));
    for (const item of APP_PLANNED) expect(planned).toContain(item);
    for (const item of ["SAST", "Secret detection", "vulnerability database"])
      expect(planned).toContain(item);
    const rest = card.slice(0, card.indexOf("Planned, not available"));
    expect(rest).not.toMatch(/SAST|Secret detection/);
    for (const item of APP_WORKS) expect(rest).toContain(item);
  });

  it("keeps the honest limits, the illustrative table and the steps", () => {
    const { container } = text(<EarlyAccess />);
    const section = container.querySelector("#app-scanning")?.textContent ?? "";
    expect(section).toMatch(/never reported as clean/);
    expect(section).toMatch(/not a penetration test/);
    expect(section).toContain("Illustrative example");
    for (const s of APP_STEPS) expect(section).toContain(s.title);
  });

  it("publishes no App Scanning allowances, prices or unlimited claims", () => {
    const { text: t } = text(<EarlyAccess />);
    expect(t).not.toMatch(/unlimited/i);
    expect(t).not.toMatch(/\d+ runs|runs per month|€|\$\s?\d/i);
  });

  it("links to the privacy notice and the terms, and makes no API request", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const { container } = text(<EarlyAccess />);
    const trust = container.querySelector("#app-scanning");
    expect(trust?.querySelector('a[href="#/privacy"]')).not.toBeNull();
    expect(trust?.querySelector('a[href="#/terms"]')).not.toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("routes, titles and the app shell", () => {
  beforeEach(() => {
    window.location.hash = "";
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });
  afterEach(() => {
    window.location.hash = "";
  });

  it("knows the four new pages and still rejects unknown names", () => {
    for (const name of ["checks", "pricing", "help", "early-access"]) {
      expect(parseHash(`#/${name}`).page).toBe(name);
      expect(PUBLIC_PAGES).not.toContain(name);
    }
    expect(parseHash("#/nope").page).toBe("not-found");
  });

  it("titles each page", () => {
    expect(titleFor("checks", false)).toBe("What we check – SecureScope");
    expect(titleFor("pricing", false)).toBe("Pricing – SecureScope");
    expect(titleFor("help", false)).toBe("Help – SecureScope");
    expect(titleFor("early-access", false)).toBe(
      "App Scanning (Early Access) – SecureScope",
    );
  });

  it.each([
    ["#/checks", "What SecureScope checks"],
    ["#/pricing", "Pricing"],
    ["#/help", "Questions"],
    ["#/early-access", "App Scanning is in Early Access"],
  ])("opens %s for a visitor who is not signed in", async (hash, heading) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) })),
    );
    window.location.hash = hash;
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: heading }),
    ).toBeInTheDocument();
  });
});
