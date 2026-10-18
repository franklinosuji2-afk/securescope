import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import FindingList from "../components/FindingList";
import { buildHash, parseHash } from "../router";
import type { Finding, ScanDetail } from "../types";

const finding: Finding = {
  id: "SS-HDR-CSP-001",
  title: "Content-Security-Policy header missing",
  severity: "medium",
  category: "headers",
  description: "No CSP was returned.",
  evidence: "header absent",
  remediation: "Add a CSP.",
};

const scan: ScanDetail = {
  id: "abc123",
  target_url: "https://example.org/",
  host: "example.org",
  status: "completed",
  score: 80,
  grade: "B",
  created_at: "2026-10-18T10:00:00Z",
  finished_at: "2026-10-18T10:00:02Z",
  counts: { medium: 1 },
  error: null,
  metadata: null,
  findings: [finding],
  score_note: "Heuristic score.",
};

function mockFetch(handler: (url: string, init?: RequestInit) => unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => ({
      ok: status < 400,
      status,
      json: async () => handler(url, init),
    })),
  );
}

beforeEach(() => {
  window.location.hash = "";
  vi.unstubAllGlobals();
});

describe("router", () => {
  it("parses and builds hashes", () => {
    expect(parseHash("#/findings?scan=abc123")).toEqual({ page: "findings", scanId: "abc123" });
    expect(parseHash("#/findings?scan=../x")).toEqual({ page: "findings", scanId: null });
    expect(parseHash("")).toEqual({ page: "overview", scanId: null });
    expect(buildHash("history", null)).toBe("#/history");
  });
});

describe("Overview", () => {
  it("shows an honest empty state and no fabricated results", () => {
    mockFetch(() => ({}));
    render(<App />);
    expect(screen.getByText("No scan yet")).toBeInTheDocument();
    expect(screen.queryByText(/Heuristic score/)).not.toBeInTheDocument();
  });

  it("keeps Start disabled until authorization is acknowledged", async () => {
    mockFetch(() => ({}));
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Target URL"), "https://example.org");
    const button = screen.getByRole("button", { name: "Start scan" });
    expect(button).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
  });

  it("shows the server error when a target is rejected", async () => {
    mockFetch(() => ({ detail: "Target resolves to a private address." }), 422);
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Target URL"), "http://internal.test");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("private address");
  });

  it("renders a completed scan loaded from the URL", async () => {
    window.location.hash = "#/?scan=abc123";
    mockFetch(() => scan);
    render(<App />);
    expect(await screen.findByText("Grade B")).toBeInTheDocument();
    expect(screen.getByText("Heuristic score.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JSON" })).toHaveAttribute("href", "/api/v1/scans/abc123/report?format=json");
  });
});

describe("FindingList", () => {
  it("expands details and exposes aria-expanded", async () => {
    render(<FindingList findings={[finding]} />);
    const toggle = screen.getByRole("button", { name: /Content-Security-Policy/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Add a CSP.")).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Add a CSP.")).toBeInTheDocument();
    expect(screen.getByText("header absent")).toBeInTheDocument();
  });
});

describe("History", () => {
  it("lists saved scans", async () => {
    window.location.hash = "#/history";
    mockFetch(() => ({ items: [scan], total: 1 }));
    render(<App />);
    await waitFor(() => expect(screen.getByText("example.org")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Open scan of example.org" })).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    window.location.hash = "#/history";
    mockFetch(() => ({ items: [], total: 0 }));
    render(<App />);
    expect(await screen.findByText("No scans yet")).toBeInTheDocument();
  });
});
