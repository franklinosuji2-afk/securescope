import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EMAIL_LINK_PAGES, addEmailLinkPages } from "./postbuild.mjs";

let dist;
beforeEach(() => {
  dist = mkdtempSync(join(tmpdir(), "ss-dist-"));
});
afterEach(() => rmSync(dist, { recursive: true, force: true }));

describe("email link pages", () => {
  it("serves the app at each address that emails contain", () => {
    writeFileSync(
      join(dist, "index.html"),
      "<!doctype html><title>app</title>",
    );
    writeFileSync(
      join(dist, "404.html"),
      "<!doctype html><title>missing</title>",
    );
    const made = addEmailLinkPages(dist);
    expect(made).toEqual(EMAIL_LINK_PAGES.map((n) => `${n}.html`));
    for (const name of EMAIL_LINK_PAGES)
      expect(readFileSync(join(dist, `${name}.html`), "utf8")).toBe(
        readFileSync(join(dist, "index.html"), "utf8"),
      );
    // The not-found page is left alone, so any other path answers 404.
    expect(readFileSync(join(dist, "404.html"), "utf8")).toContain("missing");
  });

  it("lists exactly the paths the app turns into hash routes", () => {
    const main = readFileSync(
      join(import.meta.dirname, "../src/main.tsx"),
      "utf8",
    );
    const match = /\^\\\/\(([^)]+)\)\$/.exec(main);
    expect(match?.[1]?.split("|").sort()).toEqual([...EMAIL_LINK_PAGES].sort());
  });

  it("refuses to build without the pages it depends on", () => {
    expect(() => addEmailLinkPages(dist)).toThrow(/index\.html/);
    writeFileSync(join(dist, "index.html"), "x");
    expect(() => addEmailLinkPages(dist)).toThrow(/404\.html/);
  });

  it("ships a not-found page with no scripts and the right title", () => {
    const page = readFileSync(
      join(import.meta.dirname, "../public/404.html"),
      "utf8",
    );
    expect(page).not.toMatch(/<script/i);
    expect(page).toContain("<title>Page not found");
    expect(page).toMatch(/name="robots" content="noindex"/);
  });
});
