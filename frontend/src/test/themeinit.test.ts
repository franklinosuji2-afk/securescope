import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import html from "../../index.html?raw";
import script from "../../public/theme-init.js?raw";
import themeSource from "../theme.ts?raw";

function run(): void {
  new Function(script)();
}

describe("theme-init.js (applies the saved theme before first paint)", () => {
  beforeEach(() => {
    document.head.innerHTML = '<meta name="theme-color" content="#050505">';
    document.documentElement.removeAttribute("data-theme");
    window.localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("applies a saved light theme and the matching toolbar colour", () => {
    window.localStorage.setItem("securescope-theme", "light");
    run();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#eef3f8",
    );
  });

  it("applies a saved dark theme", () => {
    window.localStorage.setItem("securescope-theme", "dark");
    run();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#050505",
    );
  });

  it("leaves the page to follow the system when nothing valid is saved", () => {
    run();
    expect(document.documentElement).not.toHaveAttribute("data-theme");
    window.localStorage.setItem("securescope-theme", "<script>");
    run();
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("does not throw when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(run).not.toThrow();
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("uses the same storage key and colours as the app", () => {
    expect(themeSource).toContain('"securescope-theme"');
    expect(themeSource).toContain('"#eef3f8"');
    expect(themeSource).toContain('"#050505"');
  });

  it("is loaded from index.html before the app, as a same-origin file (the CSP forbids inline scripts)", () => {
    expect(html).toContain('<script src="/theme-init.js"></script>');
    expect(html.indexOf("/theme-init.js")).toBeLessThan(
      html.indexOf('type="module"'),
    );
  });
});
