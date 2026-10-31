import { afterEach, describe, expect, it, vi } from "vitest";
import { createAppScan } from "../api";

function answer(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: false, status, json: async () => body })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("error messages from the server", () => {
  it("shows the message of a structured refusal, with the file it is about", async () => {
    answer(422, {
      detail: {
        code: "not_json",
        message: "The file is not valid JSON.",
        file: "package-lock.json",
      },
    });
    await expect(createAppScan("p1", [], "k")).rejects.toThrow(
      "package-lock.json: The file is not valid JSON.",
    );
  });

  it("shows a structured message without a file name as it is", async () => {
    answer(422, {
      detail: {
        code: "no_packages",
        message: "No checkable packages were found in the files.",
        file: "",
      },
    });
    await expect(createAppScan("p1", [], "k")).rejects.toThrow(
      /^No checkable packages were found in the files\.$/,
    );
  });

  it("falls back to the status for an answer it cannot read", async () => {
    answer(502, { detail: { code: 1 } });
    await expect(createAppScan("p1", [], "k")).rejects.toThrow("HTTP 502");
  });
});
