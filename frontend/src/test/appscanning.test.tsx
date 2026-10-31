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
  getAppScan: vi.fn(),
  archiveAppProject: vi.fn(),
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
  origin: "upload",
  ref: null,
  status: "completed",
  result: "completed_no_findings",
  result_text: "Completed. No findings were detected by the selected checks.",
  created_at: "2026-10-26T10:00:00Z",
  finished_at: "2026-10-26T10:00:01Z",
  counts: {},
  kinds: ["dependency"],
  inputs: [],
  checks_run: [],
  checks_skipped: [],
  scanners: [],
  findings: [],
  limitations: ["Only declared dependencies with exact versions are checked."],
  error: null,
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
    expect(
      await screen.findByText(/Runs this month: 1 of 5 used, 4 left/),
    ).toBeTruthy();
    expect(screen.getByText(/Only declared dependencies/)).toBeTruthy();
  });

  it("does not claim a vulnerability database is being queried", async () => {
    render(<AppScanning canCreate />);
    expect(await screen.findByText(/database is not connected/)).toBeTruthy();
    expect(screen.queryByText(/are looked up/)).toBeNull();
  });

  it("says what is sent when the server has lookups switched on", async () => {
    vi.mocked(api.getAppOverview).mockResolvedValue(
      overview({ lookups_available: true }),
    );
    render(<AppScanning canCreate />);
    expect(
      await screen.findByText(/looks\s+each one up in the OSV\.dev/),
    ).toBeTruthy();
    expect(
      screen.getByText(/ecosystem, name and version are sent/),
    ).toBeTruthy();
    expect(screen.queryByText(/not connected/)).toBeNull();
  });

  it("shows progress while a scan runs, then the result", async () => {
    let finish: (value: AppScan) => void = () => {};
    vi.mocked(api.createAppScan).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect((await screen.findByRole("status")).textContent).toMatch(
      /Checking 1 file/,
    );
    expect(
      (screen.getByRole("button", { name: "Checking…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    finish(scan());
    expect(
      await screen.findByText("No known vulnerabilities in these packages"),
    ).toBeTruthy();
    expect(screen.queryByText(/Checking 1 file/)).toBeNull();
  });

  it("a failed run says why", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({
        status: "failed",
        result: "scanner_error",
        result_text:
          "Scanner error. Nothing was checked and this run was not counted.",
        error:
          "The vulnerability source could not be reached, so nothing was checked.",
      }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    const status = await screen.findByRole("status");
    expect(status.className).toContain("notice-error");
    expect(status.textContent).toContain("Did not complete");
    expect(status.textContent).toContain("could not be reached");
  });

  it("shows how to fix a finding and credits the advisory data", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({
        result: "completed_findings",
        counts: { high: 1 },
        attribution: "Advisory data from OSV.dev.",
        findings: [
          {
            kind: "dependency",
            rule_id: "GHSA-x",
            title: "lodash 4.17.20 has a known vulnerability (GHSA-x)",
            severity: "high",
            description: "d",
            remediation: "Upgrade lodash to a fixed version (4.17.21).",
            package_name: "lodash",
            package_version: "4.17.20",
            fixed_versions: ["4.17.21"],
            references: [],
            aliases: [],
            path: null,
            line: null,
          },
        ],
      }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(
      await screen.findByText(/Upgrade lodash to a fixed version/),
    ).toBeTruthy();
    expect(screen.getByText("Advisory data from OSV.dev.")).toBeTruthy();
  });

  it("shows a pipeline's code findings by file and line, with the check that found them", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({
        origin: "ci",
        kinds: ["sast", "secrets"],
        result: "completed_findings",
        counts: { high: 1, medium: 1 },
        findings: [
          {
            kind: "sast",
            rule_id: "py.sql-injection",
            title: "SQL built from user input",
            severity: "high",
            description: "d",
            remediation: "Use parameters.",
            package_name: null,
            package_version: null,
            fixed_versions: [],
            references: [],
            aliases: [],
            path: "app/db.py",
            line: 42,
          },
          {
            kind: "secrets",
            rule_id: "generic-credential",
            title: "Possible credential in code",
            severity: "medium",
            description: "d",
            remediation: "Rotate it.",
            package_name: null,
            package_version: null,
            fixed_versions: [],
            references: [],
            aliases: [],
            path: "config/settings.py",
            line: null,
          },
        ],
      }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(await screen.findByText("app/db.py:42")).toBeTruthy();
    expect(screen.getByText("config/settings.py")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Findings" })).toBeTruthy();
    expect(screen.queryByText("Dependency findings")).toBeNull();
    expect(screen.queryByText("No fixed version listed")).toBeNull();
    expect(screen.getByText("Static analysis")).toBeTruthy();
    expect(screen.getByText("Secret detection")).toBeTruthy();
  });

  it("a clean pipeline run names its checks, not packages", async () => {
    vi.mocked(api.createAppScan).mockResolvedValue(
      scan({ origin: "ci", kinds: ["sast", "secrets"] }),
    );
    render(<AppScanning canCreate />);
    await upload();
    await userEvent.click(
      screen.getByRole("button", { name: "Check dependencies" }),
    );
    expect(
      await screen.findByText("No findings from these checks"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Static analysis and Secret detection ran on your pipeline/,
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText("No known vulnerabilities in these packages"),
    ).toBeNull();
  });

  it("opens an earlier run from the runs list", async () => {
    vi.mocked(api.listAppScans).mockResolvedValue([scan({ id: "old" })]);
    vi.mocked(api.getAppScan).mockResolvedValue(
      scan({
        id: "old",
        status: "incomplete",
        result: "incomplete",
        result_text: "Incomplete. Some checks could not run.",
        checks_skipped: [{ reason: "2 entries could not be checked" }],
      }),
    );
    render(<AppScanning canCreate />);
    await userEvent.click(
      await screen.findByRole("button", { name: /View result/ }),
    );
    expect(
      await screen.findByText("2 entries could not be checked"),
    ).toBeTruthy();
    expect(api.getAppScan).toHaveBeenCalledWith("old");
    expect(screen.getByRole("button", { name: /Shown above/ })).toBeTruthy();
  });

  it("archives the selected project after confirmation, freeing its place", async () => {
    vi.mocked(api.archiveAppProject).mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AppScanning canCreate />);
    vi.mocked(api.listAppProjects).mockResolvedValue([]);
    await userEvent.click(
      await screen.findByRole("button", { name: "Archive this project" }),
    );
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining("Archive web?"),
    );
    expect(api.archiveAppProject).toHaveBeenCalledWith("p1");
    expect(await screen.findByText("No projects yet")).toBeTruthy();
    confirm.mockRestore();
  });

  it("does nothing when archiving is not confirmed", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AppScanning canCreate />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Archive this project" }),
    );
    expect(api.archiveAppProject).not.toHaveBeenCalled();
    confirm.mockRestore();
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

  it("the runs list says where each run came from and how many findings it has, without a score", async () => {
    vi.mocked(api.listAppScans).mockResolvedValue([
      {
        ...scan({ id: "s2" }),
        origin: "ci",
        ref: "refs/heads/main",
        result_text: "Completed. Findings were detected.",
        counts: { medium: 1, high: 4, low: 0 },
      },
      { ...scan({ id: "s3" }), origin: "upload", ref: null },
    ]);
    render(<AppScanning canCreate />);
    const items = await screen.findAllByRole("listitem");
    const text = items.map((i) => i.textContent ?? "").join("\n");
    expect(text).toMatch(
      /\(CI pipeline, refs\/heads\/main\): Completed\. Findings were detected\. 4 high, 1 medium\./,
    );
    expect(text).toMatch(/\(Browser upload\): Completed\. No findings/);
    expect(text).not.toMatch(/score|grade|secure\b/i);
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
            kind: "dependency",
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
            line: null,
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

describe("usage display", () => {
  const withUsage = (plan: string, usage: Record<string, unknown>) =>
    vi.mocked(api.getAppOverview).mockResolvedValue(
      overview({
        plan,
        usage: { ...overview().usage, ...usage },
      } as Partial<AppOverview>),
    );

  it.each([
    ["Free", 5, 1, "0 of 5 used, 5 left", "0 of 1 used, 1 left"],
    [
      "Professional",
      100,
      10,
      "0 of 100 used, 100 left",
      "0 of 10 used, 10 left",
    ],
    ["Agency", 500, 50, "0 of 500 used, 500 left", "0 of 50 used, 50 left"],
  ])(
    "shows the configured limits for %s",
    async (plan, runs, projects, r, p) => {
      withUsage(plan, {
        runs_used: 0,
        runs_limit: runs,
        projects_used: 0,
        projects_limit: projects,
      });
      render(<AppScanning canCreate />);
      expect(
        await screen.findByText(
          new RegExp(`Runs this month: ${r}.*Projects: ${p}`),
        ),
      ).toBeTruthy();
    },
  );

  it("says no limit only for the internal plan", async () => {
    withUsage("Internal", { runs_limit: null, projects_limit: null });
    render(<AppScanning canCreate />);
    expect(await screen.findByText(/1 used, no limit/)).toBeTruthy();
    expect(screen.queryByText(/unlimited/i)).toBeNull();
  });

  it.each([
    ["a missing limit on a customer plan", "Free", { runs_limit: null }],
    ["an undefined limit", "Professional", { projects_limit: undefined }],
    ["a negative count", "Agency", { runs_used: -1 }],
    ["a non-numeric count", "Free", { projects_used: "many" }],
  ])(
    "shows usage as unavailable, not unlimited, for %s",
    async (_n, plan, bad) => {
      withUsage(plan, bad);
      render(<AppScanning canCreate />);
      expect(
        await screen.findByText(/usage figures are unavailable/),
      ).toBeTruthy();
      expect(screen.queryByText(/unlimited|undefined|NaN/i)).toBeNull();
    },
  );

  it("says when the allowance is used up", async () => {
    withUsage("Free", { runs_used: 5, runs_limit: 5 });
    render(<AppScanning canCreate />);
    expect(
      await screen.findByText(/5 of 5 used, 0 left \(run limit reached\)/),
    ).toBeTruthy();
  });
});

describe("menu entry", () => {
  const user = {
    id: "u1",
    email: "a@example.org",
    email_verified: true,
    organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
  };
  function stub(appStatus: number, who: object = user, appBody?: object) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
        if (path === "/app/overview")
          return {
            ok: appStatus === 200,
            status: appStatus,
            json: async () => appBody ?? (appStatus === 200 ? overview() : {}),
          };
        const body =
          path === "/auth/me"
            ? who
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
  it("a direct link while the feature is off explains instead of showing a blank page", async () => {
    stub(404);
    window.location.hash = "#/app-scanning";
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(
      await screen.findByText(/not switched on for this workspace/),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Read about Early Access" }),
    ).toBeTruthy();
    window.location.hash = "";
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
  it("makes no App Scanning request for an unverified user", async () => {
    stub(200, { ...user, email_verified: false });
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/auth/me"),
        expect.anything(),
      ),
    );
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole("link", { name: "App Scanning" })).toBeNull();
    const calls = vi
      .mocked(globalThis.fetch)
      .mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes("/app/"))).toBe(false);
  });
  it("is hidden when the answer is not an overview", async () => {
    stub(200, user, {});
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
});
