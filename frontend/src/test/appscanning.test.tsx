import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import AppScanning from "../pages/AppScanning";
import type { AppOverview, AppScan } from "../api";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getAppOverview: vi.fn(),
  listAppProjects: vi.fn(),
  listAppScans: vi.fn(),
  createAppProject: vi.fn(),
  createAppScan: vi.fn(),
}));
import * as api from "../api";

const overview = (extra: Partial<AppOverview> = {}): AppOverview => ({
  plan: "Free",
  usage: {
    runs_used: 1,
    runs_limit: 5,
    projects_used: 1,
    projects_limit: 1,
    period_end: "2026-11-01T00:00:00Z",
  },
  supported_files: ["package-lock.json", "requirements.txt"],
  max_files: 5,
  max_file_bytes: 2_000_000,
  ci_tokens_available: false,
  limitations: ["Only declared dependencies with exact versions are checked."],
  ...extra,
});

const scan = (extra: Partial<AppScan> = {}): AppScan => ({
  id: "s1",
  project_id: "p1",
  status: "completed",
  result: "completed_no_findings",
  result_text: "Completed. No findings were detected by the selected checks.",
  created_at: "2026-10-26T10:00:00Z",
  finished_at: "2026-10-26T10:00:01Z",
  counts: {},
  inputs: [],
  checks_run: [],
  checks_skipped: [],
  scanners: [],
  findings: [],
  limitations: ["Only declared dependencies with exact versions are checked."],
  replayed: false,
  ...extra,
});

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getAppOverview).mockResolvedValue(overview());
  vi.mocked(api.listAppProjects).mockResolvedValue([
    {
      id: "p1",
      name: "web",
      source: "upload",
      created_at: "2026-10-01T00:00:00Z",
    },
  ]);
  vi.mocked(api.listAppScans).mockResolvedValue([]);
});

async function upload(content = "{}") {
  const file = new File([content], "package-lock.json", {
    type: "application/json",
  });
  await userEvent.upload(
    await screen.findByLabelText(/Dependency files/),
    file,
  );
}

describe("App Scanning page", () => {
  it("shows usage and the limitations before any scan", async () => {
    render(<AppScanning canCreate />);
    expect(await screen.findByText(/Runs this month: 1 of 5/)).toBeTruthy();
    expect(screen.getByText(/Only declared dependencies/)).toBeTruthy();
  });

  it("a clean result says no findings from the selected checks, never 'secure'", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(scan());
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(await screen.findByText(/selected checks/)).toBeTruthy();
    expect(screen.queryByText(/\bsecure\b/i)).toBeNull();
    expect(screen.queryByText(/score|grade/i)).toBeNull();
  });

  it("an incomplete result is shown as a problem, not as success, with what was not checked", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({
        status: "incomplete",
        result: "incomplete",
        result_text: "Incomplete. Some checks could not be completed.",
        checks_skipped: [{ reason: "no answer for 1 packages" }],
      }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(await screen.findByText(/no answer for 1 packages/)).toBeTruthy();
    expect(screen.getByRole("status").className).toContain("notice-error");
  });

  it("renders findings as text and only links https references", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({
        result: "completed_findings",
        counts: { high: 1 },
        findings: [
          {
            rule_id: "GHSA-x",
            title: "<img src=x onerror=alert(1)>",
            severity: "high",
            description: "d",
            remediation: "r",
            package_name: "lodash",
            package_version: "4.17.20",
            fixed_versions: ["4.17.21"],
            references: ["https://example.com/a", "javascript:alert(1)"],
            aliases: [],
            path: null,
          },
        ],
      }),
    );
    const { container } = render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(
      await screen.findByText("<img src=x onerror=alert(1)>"),
    ).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    const hrefs = Array.from(container.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toContain("https://example.com/a");
    expect(hrefs.some((h) => h?.startsWith("javascript"))).toBe(false);
    expect(screen.getByText("4.17.21")).toBeTruthy();
  });

  it("shows the server's refusal message and lets the user retry", async () => {
    vi.mocked(api.createAppScan).mockRejectedValue(
      new Error("Monthly limit reached."),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Monthly limit",
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Check dependencies",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });

  it("refuses an oversized file in the browser before sending anything", async () => {
    vi.mocked(api.getAppOverview).mockResolvedValue(
      overview({ max_file_bytes: 10 }),
    );
    render(<AppScanning canCreate />);
    await upload("x".repeat(50));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "larger than",
    );
    expect(api.createAppScan).not.toHaveBeenCalled();
  });

  it("a role that cannot create sees results but no forms", async () => {
    render(<AppScanning canCreate={false} />);
    expect(await screen.findByText(/cannot start scans/)).toBeTruthy();
    expect(screen.queryByLabelText(/Dependency files/)).toBeNull();
    expect(screen.queryByLabelText(/New project name/)).toBeNull();
  });

  it("an empty workspace is told to add a project first", async () => {
    vi.mocked(api.listAppProjects).mockResolvedValue([]);
    render(<AppScanning canCreate />);
    expect(await screen.findByText("No projects yet")).toBeTruthy();
  });

  it("an unavailable service shows an error, not a blank page", async () => {
    vi.mocked(api.getAppOverview).mockRejectedValue(new Error("Not found."));
    render(<AppScanning canCreate />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Not found",
    );
  });
});

describe("menu entry", () => {
  const user = {
    id: "u1",
    email: "a@example.org",
    email_verified: true,
    organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
  };
  function stub(appStatus: number) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
        if (path === "/app/overview")
          return {
            ok: appStatus === 200,
            status: appStatus,
            json: async () => ({}),
          };
        const body =
          path === "/auth/me"
            ? user
            : path === "/scans" || path === "/targets"
              ? { items: [], total: 0 }
              : {};
        return { ok: true, status: 200, json: async () => body };
      }),
    );
  }
  it("is hidden while the server has the feature off", async () => {
    stub(404);
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    await screen.findAllByText("Targets");
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/app/overview"),
        expect.anything(),
      ),
    );
    expect(screen.queryByRole("link", { name: "App Scanning" })).toBeNull();
  });
  it("appears when the server has it on", async () => {
    stub(200);
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(
      await screen.findByRole("link", { name: "App Scanning" }),
    ).toBeTruthy();
  });
});
