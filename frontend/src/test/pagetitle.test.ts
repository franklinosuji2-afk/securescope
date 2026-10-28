import { describe, expect, it } from "vitest";
import { DEFAULT_TITLE, SELF_TITLED, titleFor } from "../pageTitle";

describe("page titles", () => {
  it("names each page after what the person sees on it", () => {
    expect(titleFor("history", true)).toBe("Scan history – SecureScope");
    expect(titleFor("health", true)).toBe("Platform health – SecureScope");
    expect(titleFor("login", false)).toBe("Sign in – SecureScope");
    expect(titleFor("privacy", false)).toBe("Privacy notice – SecureScope");
  });

  it("keeps the home page title for visitors who are not signed in", () => {
    expect(titleFor("overview", false)).toBe(DEFAULT_TITLE);
    expect(titleFor("overview", true)).toBe("Overview – SecureScope");
  });

  it("leaves the pages that set their own title alone", () => {
    for (const page of SELF_TITLED) expect(titleFor(page, true)).toBeNull();
  });
});
