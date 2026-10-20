import { describe, expect, it } from "vitest";
import text from "../../public/.well-known/security.txt?raw";

describe("security.txt (RFC 9116)", () => {
  it("has a Contact line", () => {
    expect(text).toMatch(/^Contact: (mailto:|https:\/\/)\S+$/m);
  });

  it("has an Expires date that is still in the future and under a year ahead", () => {
    const match = /^Expires: (\S+)$/m.exec(text);
    expect(match).not.toBeNull();
    const expires = new Date(match![1] ?? "").getTime();
    expect(expires).toBeGreaterThan(Date.now());
    expect(expires).toBeLessThan(Date.now() + 366 * 24 * 3600 * 1000);
  });
});
