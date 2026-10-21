import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import PdfReportButton from "../components/PdfReportButton";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return { ok: status < 400, status, json: async () => body };
    }),
  );
  return calls;
}

describe("the PDF report button", () => {
  it("asks the server for the report, then downloads it through the link it returns", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const calls = stubFetch(200, {
      report_id: "SSR-ABC",
      url: "/api/v1/scans/s1/report/pdf/download?org=o1&expires=1&sig=x",
      expires_at: "2026-10-22T10:05:00Z",
      size_bytes: 1000,
      created_at: "2026-10-22T10:00:00Z",
    });
    render(<PdfReportButton scanId="s1" host="a.test" />);
    await userEvent
      .setup()
      .click(
        screen.getByRole("button", { name: "Download PDF report for a.test" }),
      );
    expect(calls[0]?.url).toBe("/api/v1/scans/s1/report/pdf");
    expect(assign).toHaveBeenCalledWith(
      "/api/v1/scans/s1/report/pdf/download?org=o1&expires=1&sig=x",
    );
  });

  it("shows the server's reason and downloads nothing when the report cannot be made", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    stubFetch(409, {
      detail: "A report is available once a scan has finished successfully.",
    });
    render(<PdfReportButton scanId="s1" />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Download PDF report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "once a scan has finished successfully",
    );
    expect(assign).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Download PDF report" }),
    ).toBeEnabled();
  });
});
