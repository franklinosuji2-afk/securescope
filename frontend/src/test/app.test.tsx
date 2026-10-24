import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import FindingDetail from "../components/FindingDetail";
import FindingRows from "../components/FindingRows";
import { filterFindings } from "../pages/Findings";
import { buildHash, parseHash } from "../router";
import type { Finding, Role, ScanDetail, Target, User } from "../types";

const finding: Finding = {
  id: "SS-HDR-CSP-001",
  title: "Content-Security-Policy header missing",
  severity: "medium",
  category: "headers",
  description: "No CSP was returned.",
  evidence: "header absent",
  remediation: "Add a CSP.",
  confidence: "high",
  fingerprint: "a".repeat(32),
  status: "open",
  status_note: null,
  first_seen_at: "2026-10-18T10:00:00Z",
  last_seen_at: "2026-10-18T10:00:00Z",
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

function userWith(role: Role): User {
  return {
    id: "u1",
    email: "alice@example.org",
    email_verified: true,
    organizations: [{ id: "org1", name: "Alice Org", slug: "alice-org", role }],
  };
}

type Handler = (url: string, init?: RequestInit) => unknown;
interface Mock {
  calls: { url: string; init?: RequestInit }[];
}

/** Routes fetch by URL. `/auth/me` answers with `me` (null means signed out, i.e. 401). */
function mockApi(
  handler: Handler,
  me: User | null = userWith("OWNER"),
  status: number | ((url: string, init?: RequestInit) => number) = 200,
): Mock {
  const mock: Mock = { calls: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      mock.calls.push({ url, init });
      if (url.endsWith("/auth/me")) {
        return me
          ? { ok: true, status: 200, json: async () => me }
          : {
              ok: false,
              status: 401,
              json: async () => ({ detail: "Authentication required." }),
            };
      }
      const code = typeof status === "function" ? status(url, init) : status;
      return {
        ok: code < 400,
        status: code,
        json: async () => handler(url, init),
      };
    }),
  );
  return mock;
}

function mockFetch(
  handler: Handler,
  status: number | ((url: string, init?: RequestInit) => number) = 200,
) {
  return mockApi(handler, userWith("OWNER"), status);
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

beforeEach(() => {
  window.location.hash = "";
  vi.unstubAllGlobals();
});

describe("router", () => {
  it("parses and builds hashes", () => {
    expect(parseHash("#/findings?scan=abc123")).toEqual({
      page: "findings",
      scanId: "abc123",
      findingId: null,
      token: null,
      compareWith: null,
    });
    expect(parseHash("#/findings?scan=../x")).toEqual({
      page: "findings",
      scanId: null,
      findingId: null,
      token: null,
      compareWith: null,
    });
    expect(parseHash("")).toEqual({
      page: "overview",
      scanId: null,
      findingId: null,
      token: null,
      compareWith: null,
    });
    expect(buildHash("history", null)).toBe("#/history");
  });
});

describe("Overview", () => {
  it("shows an honest empty state and no fabricated results", async () => {
    mockFetch(() => ({}));
    renderApp();
    expect(await screen.findByText(/No scan yet/)).toBeInTheDocument();
    expect(screen.queryByText(/Heuristic score/)).not.toBeInTheDocument();
  });

  it("keeps Start disabled until authorization is acknowledged", async () => {
    mockFetch(() => ({}));
    renderApp();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Target URL"),
      "https://example.org",
    );
    const button = screen.getByRole("button", { name: "Start scan" });
    expect(button).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
  });

  it("shows the server error when a target is rejected", async () => {
    mockFetch(
      () => ({ detail: "Target resolves to a private address." }),
      (_url, init) => (init?.method === "POST" ? 422 : 200),
    );
    renderApp();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Target URL"),
      "http://internal.test",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "private address",
    );
  });

  it("renders a completed scan loaded from the URL", async () => {
    window.location.hash = "#/?scan=abc123";
    mockFetch(() => scan);
    renderApp();
    expect(await screen.findByText("Grade B")).toBeInTheDocument();
    expect(screen.getByText("Heuristic score.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JSON" })).toHaveAttribute(
      "href",
      "/api/v1/scans/abc123/report?format=json&org=org1",
    );
  });
});

describe("Findings", () => {
  const many: Finding[] = [
    finding,
    {
      ...finding,
      id: "SS-HDR-HSTS-001",
      title: "Strict-Transport-Security header is missing",
      severity: "high",
      category: "Security headers",
    },
    {
      ...finding,
      id: "SS-DISC-SRV-002",
      title: "Server header is present",
      severity: "info",
      category: "Information disclosure",
    },
  ];

  it("links each row to its finding with a text severity label", () => {
    render(<FindingRows scanId="abc123" findings={[finding]} />);
    const link = screen.getByRole("link", {
      name: /Content-Security-Policy header missing/,
    });
    expect(link).toHaveAttribute(
      "href",
      "#/findings?scan=abc123&finding=SS-HDR-CSP-001",
    );
    expect(screen.getByText("Medium")).toBeInTheDocument();
  });

  it("filters, searches and sorts", () => {
    const base = {
      severity: "all" as const,
      category: "all",
      query: "",
      sort: "severity" as const,
    };
    expect(filterFindings(many, base).map((f) => f.id)).toEqual([
      "SS-HDR-HSTS-001",
      "SS-HDR-CSP-001",
      "SS-DISC-SRV-002",
    ]);
    expect(
      filterFindings(many, { ...base, severity: "info" }).map((f) => f.id),
    ).toEqual(["SS-DISC-SRV-002"]);
    expect(
      filterFindings(many, { ...base, category: "Security headers" }),
    ).toHaveLength(1);
    expect(
      filterFindings(many, { ...base, query: "server" }).map((f) => f.id),
    ).toEqual(["SS-DISC-SRV-002"]);
    expect(filterFindings(many, { ...base, sort: "title" })[0]?.id).toBe(
      "SS-HDR-CSP-001",
    );
  });

  it("shows evidence as plain text and never claims a fix", async () => {
    const hostile = { ...finding, evidence: "<img src=x onerror=alert(1)>" };
    mockFetch(() => ({}));
    const { container } = render(
      <AuthProvider>
        <FindingDetail
          scan={{ ...scan, findings: [hostile] }}
          finding={hostile}
        />
      </AuthProvider>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(
      await screen.findByText("<img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "How to verify" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not mark a finding as fixed/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Content-Security-Policy/ }),
    ).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("opens a finding from the URL and filters the list", async () => {
    window.location.hash = "#/findings?scan=abc123&finding=SS-HDR-CSP-001";
    mockFetch(() => scan);
    renderApp();
    expect(
      await screen.findByRole("heading", {
        name: "Content-Security-Policy header missing",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /All findings/ }),
    ).toBeInTheDocument();
  });

  it("explains when a finding id is not in the scan", async () => {
    window.location.hash = "#/findings?scan=abc123&finding=SS-NOPE-1";
    mockFetch(() => scan);
    renderApp();
    expect(
      await screen.findByText("That finding is not part of this scan."),
    ).toBeInTheDocument();
  });

  it("shows a failed scan as failed, not as zero findings", async () => {
    window.location.hash = "#/findings?scan=abc123";
    mockFetch(() => ({
      ...scan,
      status: "failed",
      error: "Could not connect.",
      findings: [],
      counts: {},
    }));
    renderApp();
    expect(await screen.findByText("Could not connect.")).toBeInTheDocument();
    expect(
      screen.queryByText("No findings from these checks"),
    ).not.toBeInTheDocument();
  });
});

describe("Finding status", () => {
  const url = "#/findings?scan=abc123&finding=SS-HDR-CSP-001";

  it("lets an analyst change the status and reloads the scan", async () => {
    window.location.hash = url;
    let status = "open";
    const mock = mockApi((_url, init) => {
      if (init?.method === "PATCH") {
        status = JSON.parse(String(init.body)).status;
        return undefined;
      }
      return { ...scan, findings: [{ ...finding, status }] };
    });
    renderApp();
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Change status"),
      "accepted_risk",
    );
    await user.type(screen.getByLabelText("Note (optional)"), "static site");
    await user.click(screen.getByRole("button", { name: "Save status" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Status saved."),
    );
    const patch = mock.calls.find((c) => c.init?.method === "PATCH");
    expect(patch?.url).toBe(`/api/v1/findings/${"a".repeat(32)}`);
    expect(JSON.parse(String(patch?.init?.body))).toEqual({
      status: "accepted_risk",
      note: "static site",
    });
    expect(patch?.init?.headers).toHaveProperty("X-CSRF-Token");
    await waitFor(() =>
      expect(screen.getAllByText("Accepted risk").length).toBeGreaterThan(0),
    );
  });

  it("offers only the statuses a person may set, never resolved", async () => {
    window.location.hash = url;
    mockApi(() => scan);
    renderApp();
    const select = await screen.findByLabelText("Change status");
    const options = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(options).toEqual(["Open", "Accepted risk", "False positive"]);
  });

  it("hides the control from roles that cannot triage", async () => {
    window.location.hash = url;
    mockApi(() => scan, userWith("VIEWER"));
    renderApp();
    expect(
      await screen.findByText(/can read statuses but not change them/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Change status")).not.toBeInTheDocument();
  });

  it("explains a resolved finding and marks heuristic findings", async () => {
    window.location.hash = url;
    mockApi(() => ({
      ...scan,
      findings: [{ ...finding, status: "resolved", confidence: "medium" }],
    }));
    renderApp();
    expect(
      await screen.findByText(/no longer reported it/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Heuristic match, not confirmed/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Medium confidence/)).toBeInTheDocument();
  });

  it("filters the list by status", () => {
    const base = {
      severity: "all" as const,
      category: "all",
      query: "",
      sort: "severity" as const,
    };
    const list: Finding[] = [
      finding,
      { ...finding, id: "X", status: "resolved" },
    ];
    expect(
      filterFindings(list, { ...base, status: "resolved" }).map((f) => f.id),
    ).toEqual(["X"]);
    expect(filterFindings(list, { ...base, status: "all" })).toHaveLength(2);
  });
});

describe("Theme", () => {
  it("switches between dark and light", async () => {
    window.location.hash = "#/";
    mockFetch(() => scan);
    renderApp();
    const toggle = await screen.findByRole("button", {
      name: /Switch to (light|dark) theme/,
    });
    const before = document.documentElement.getAttribute("data-theme");
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(
      before,
    );
  });
});

describe("History", () => {
  it("lists saved scans", async () => {
    window.location.hash = "#/history";
    mockFetch(() => ({ items: [scan], total: 1 }));
    renderApp();
    await waitFor(() =>
      expect(screen.getByText("example.org")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Open scan of example.org" }),
    ).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    window.location.hash = "#/history";
    mockFetch(() => ({ items: [], total: 0 }));
    renderApp();
    expect(await screen.findByText("No scans yet")).toBeInTheDocument();
  });
});

describe("Authentication", () => {
  it("shows the public home page to a visitor and keeps the app behind sign-in", async () => {
    mockApi(() => ({}), null);
    renderApp();
    expect(
      await screen.findByRole("heading", { level: 1, name: /Find the gaps/ }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Create free account" })[0],
    ).toHaveAttribute("href", "#/register");
    expect(screen.getByRole("link", { name: "Impressum" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Target URL")).not.toBeInTheDocument();
  });

  it("offers the sample PDF report on the home page, labelled as a demonstration", async () => {
    mockApi(() => ({}), null);
    renderApp();
    const section = (
      await screen.findByRole("heading", { name: /what you hand over/ })
    ).closest("section") as HTMLElement;
    const download = within(section).getByRole("link", {
      name: "Download the sample PDF",
    });
    expect(download).toHaveAttribute("href", "/sample-report.pdf");
    expect(section.textContent).toMatch(/not a real customer or scan/);
    expect(
      within(section).getByRole("img", {
        name: /sample website security report/,
      }),
    ).toHaveAttribute("src", "/sample-report-cover.webp");
  });

  it("asks for sign-in on an app page when there is no session", async () => {
    window.location.hash = "#/targets";
    mockApi(() => ({}), null);
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Sign in required" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Target URL")).not.toBeInTheDocument();
  });

  it("shows a generic server error on a failed login and does not enter the app", async () => {
    window.location.hash = "#/login";
    mockApi(() => ({ detail: "Invalid email or password." }), null, 401);
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "a@b.co");
    await user.type(screen.getByLabelText("Password"), "wrong-password-123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid email or password.",
    );
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
  });

  it("registers and enters the app", async () => {
    window.location.hash = "#/register";
    const me = userWith("OWNER");
    const mock = mockApi(() => me, null, 201);
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "alice@example.org");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByLabelText("Target URL")).toBeInTheDocument();
    const post = mock.calls.find((c) => c.url.endsWith("/auth/register"));
    expect(post?.init?.method).toBe("POST");
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      email: "alice@example.org",
    });
  });

  it("sends the CSRF header and organization header on state-changing requests", async () => {
    document.cookie = "ss_csrf=csrf-token-value";
    const mock = mockFetch(() => ({}), 202);
    renderApp();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Target URL"),
      "https://example.org",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    await waitFor(() =>
      expect(
        mock.calls.some(
          (c) => c.url.endsWith("/scans") && c.init?.method === "POST",
        ),
      ).toBe(true),
    );
    const call = mock.calls.find(
      (c) => c.url.endsWith("/scans") && c.init?.method === "POST",
    );
    const headers = call?.init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("csrf-token-value");
    expect(headers["X-Organization-Id"]).toBe("org1");
  });

  it("sends one Idempotency-Key per scan request and reuses it after a failed attempt", async () => {
    let posts = 0;
    const mock = mockFetch(
      () => ({}),
      (url, init) => {
        if (!url.endsWith("/scans") || init?.method !== "POST") return 200;
        posts += 1;
        return posts === 1 ? 500 : 202;
      },
    );
    renderApp();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Target URL"),
      "https://example.org",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    await waitFor(() => expect(posts).toBe(1));
    await user.click(await screen.findByRole("button", { name: "Start scan" }));
    await waitFor(() => expect(posts).toBe(2));
    const keys = mock.calls
      .filter((c) => c.url.endsWith("/scans") && c.init?.method === "POST")
      .map(
        (c) => (c.init?.headers as Record<string, string>)["Idempotency-Key"],
      );
    expect(keys).toHaveLength(2);
    expect(keys[0]).toMatch(/^[A-Za-z0-9_.:-]{8,80}$/);
    expect(keys[1]).toBe(keys[0]); // the server's answer was lost, so the retry is the same request
  });

  it("hides the scan form from viewers", async () => {
    mockApi(() => ({}), userWith("VIEWER"));
    renderApp();
    expect(await screen.findByText(/cannot start scans/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Target URL")).not.toBeInTheDocument();
  });

  it("signs out", async () => {
    const mock = mockFetch(() => ({}), 204);
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() =>
      expect(mock.calls.some((c) => c.url.endsWith("/auth/logout"))).toBe(true),
    );
    expect(
      await screen.findByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
});

describe("Team", () => {
  const detail = {
    ...userWith("OWNER").organizations[0],
    members: [
      {
        user_id: "u1",
        email: "alice@example.org",
        role: "OWNER",
        joined_at: "2026-10-18T10:00:00Z",
      },
      {
        user_id: "u2",
        email: "bob@example.org",
        role: "VIEWER",
        joined_at: "2026-10-18T11:00:00Z",
      },
    ],
  };

  it("lets owners manage members", async () => {
    window.location.hash = "#/team";
    mockApi(
      (url) => (url.endsWith("/invitations") ? [] : detail),
      userWith("OWNER"),
    );
    renderApp();
    expect(await screen.findByText("bob@example.org")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove bob@example.org" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Invite by email" }),
    ).toBeInTheDocument();
  });

  it("is read-only for members", async () => {
    window.location.hash = "#/team";
    mockApi(() => detail, userWith("MEMBER"));
    renderApp();
    expect(await screen.findByText("bob@example.org")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Invite by email" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove bob@example.org" }),
    ).not.toBeInTheDocument();
  });
});

const targetBase: Target = {
  id: "t1",
  hostname: "example.org",
  status: "pending",
  challenge_token: "a".repeat(32),
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: null,
  verification_method: null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T10:00:00Z",
  dns_record_name: "_securescope-challenge.example.org",
  dns_record_value: "securescope-verification=" + "a".repeat(32),
  http_file_url: "https://example.org/.well-known/securescope-verification.txt",
  http_file_content: "securescope-verification=" + "a".repeat(32),
};

describe("Integrations", () => {
  it("asks for a verified site before offering alerts and badges", async () => {
    window.location.hash = "#/integrations";
    mockFetch(() => ({ items: [targetBase] }));
    renderApp();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Integrations" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/need at least one verified site/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Webhook alerts" }),
    ).not.toBeInTheDocument();
  });

  it("points to the Integrations page from Targets once a site is verified", async () => {
    window.location.hash = "#/targets";
    mockFetch(() => ({ items: [{ ...targetBase, status: "verified" }] }));
    renderApp();
    const link = await screen.findByRole("link", {
      name: "Integrations",
      hidden: true,
    });
    expect(link).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Webhook alerts" }),
    ).not.toBeInTheDocument();
  });

  it("lists Integrations in the main navigation", async () => {
    window.location.hash = "#/integrations";
    mockFetch(() => ({ items: [] }));
    renderApp();
    const nav = await screen.findByRole("navigation", {
      name: "Primary",
      hidden: true,
    });
    expect(nav.querySelector('a[href="#/integrations"]')).not.toBeNull();
  });
});

describe("Targets", () => {
  it("shows exact DNS and file instructions for an unverified domain", async () => {
    window.location.hash = "#/targets";
    mockFetch(() => ({ items: [targetBase] }));
    renderApp();
    expect(
      await screen.findByText("_securescope-challenge.example.org"),
    ).toBeInTheDocument();
    // The same value is shown for the DNS record and for the file content.
    expect(
      screen.getAllByText("securescope-verification=" + "a".repeat(32), {
        selector: "dd code",
      }),
    ).toHaveLength(2);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify DNS record" }),
    ).toBeEnabled();
  });

  it("shows the server's reason when verification fails and never claims success", async () => {
    window.location.hash = "#/targets";
    // Like the real server, the list returned after a failed check carries the reason.
    let current = targetBase;
    const mock = mockFetch((url) => {
      if (url.endsWith("/verify")) {
        current = {
          ...targetBase,
          last_check_error:
            "No TXT record was found at _securescope-challenge.example.org.",
        };
        return current;
      }
      return { items: [current] };
    });
    renderApp();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Verify DNS record" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No TXT record was found",
    );
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
    const call = mock.calls.find((c) => c.url.endsWith("/verify"));
    expect(JSON.parse(String(call?.init?.body))).toEqual({ method: "dns_txt" });
  });

  it("requires an explicit confirmation before removing a target", async () => {
    window.location.hash = "#/targets";
    const mock = mockFetch(() => ({ items: [targetBase] }));
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    expect(mock.calls.some((c) => c.init?.method === "DELETE")).toBe(false);
    await user.click(
      screen.getByRole("button", { name: /Confirm removal of example.org/ }),
    );
    await waitFor(() =>
      expect(mock.calls.some((c) => c.init?.method === "DELETE")).toBe(true),
    );
  });

  it("hides management controls from viewers", async () => {
    window.location.hash = "#/targets";
    mockApi(
      () => ({
        items: [
          {
            ...targetBase,
            status: "verified",
            verified_at: "2026-10-18T11:00:00Z",
            verification_method: "dns_txt",
          },
        ],
      }),
      userWith("VIEWER"),
    );
    renderApp();
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Domain name")).not.toBeInTheDocument();
  });

  it("points to Targets when a scan is refused because ownership is unverified", async () => {
    mockFetch(
      () => ({
        detail:
          "Ownership of example.org has not been verified. Add and verify it under Targets first.",
      }),
      (_url, init) => (init?.method === "POST" ? 403 : 200),
    );
    renderApp();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Target URL"),
      "https://example.org",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "has not been verified",
    );
    expect(screen.getByRole("link", { name: "Go to Targets" })).toHaveAttribute(
      "href",
      "#/targets",
    );
  });
});

describe("Overview guidance and posture", () => {
  const verified: Target = {
    id: "t1",
    hostname: "example.org",
    status: "verified",
    challenge_token: "t".repeat(20),
    challenge_expires_at: "2026-10-20T00:00:00Z",
    verified_at: "2026-10-18T10:00:00Z",
    verification_method: "dns_txt",
    last_check_at: null,
    last_check_error: null,
    created_at: "2026-10-18T09:00:00Z",
    dns_record_name: "",
    dns_record_value: "",
    http_file_url: "",
    http_file_content: "",
  };
  const site = {
    host: "example.org",
    latest_scan_id: "abc123",
    score: 84,
    grade: "B",
    scanned_at: "2026-10-18T12:00:00Z",
    previous_score: null as number | null,
    score_change: null as number | null,
    open_counts: { medium: 1 },
    open_total: 1,
    top_finding: null,
    history: [
      { scan_id: "abc123", score: 84, scanned_at: "2026-10-18T12:00:00Z" },
    ],
  };
  const topFinding = {
    host: "example.org",
    scan_id: "abc123",
    finding_id: "SS-HDR-CSP-001",
    title: "Content-Security-Policy header missing",
    severity: "medium",
    confidence: "high",
    remediation: "Add a CSP.",
  };
  const empty = { sites: [], fix_first: null, other_open: 0 };
  const scanned = {
    sites: [{ ...site, top_finding: topFinding }],
    fix_first: topFinding,
    other_open: 0,
  };

  function route(targets: Target[], overview: unknown): Handler {
    return (url) => {
      if (url.includes("/targets")) return { items: targets };
      if (url.includes("/overview")) return overview;
      if (url.includes("/scans/")) return scan;
      return {};
    };
  }

  it("walks a new user through the first step", async () => {
    mockFetch(route([], empty));
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Get your first result" }),
    ).toBeInTheDocument();
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current).toHaveTextContent("Add the site you want to check");
    expect(screen.getByRole("link", { name: "Add a site" })).toHaveAttribute(
      "href",
      "#/targets",
    );
    expect(screen.queryByText("Fix this first")).not.toBeInTheDocument();
  });

  it("offers verified sites as one-click choices and fills the URL", async () => {
    mockFetch(route([verified], empty));
    renderApp();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "example.org" }),
    );
    expect(screen.getByLabelText("Target URL")).toHaveValue(
      "https://example.org/",
    );
    expect(screen.getByRole("listitem", { current: "step" })).toHaveTextContent(
      "Run your first scan",
    );
  });

  it("shows what to fix first, and drops the setup guide, once a scan has completed", async () => {
    mockFetch(route([verified], scanned));
    renderApp();
    expect(
      await screen.findByRole("heading", { name: "Fix this first" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Get your first result" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "See the evidence and fix" }),
    ).toHaveAttribute("href", "#/findings?scan=abc123&finding=SS-HDR-CSP-001");
    const card = screen.getByRole("listitem", { name: "example.org" });
    expect(card).toHaveTextContent("Grade B");
    expect(card).toHaveTextContent("First scan of this site");
    expect(card).toHaveTextContent("1 open");
  });

  it("says nothing is open when the server reports no open findings", async () => {
    const clean = {
      sites: [{ ...site, open_counts: {}, open_total: 0 }],
      fix_first: null,
      other_open: 0,
    };
    mockFetch(route([verified], clean));
    renderApp();
    expect(await screen.findByText(/Nothing open/)).toBeInTheDocument();
    expect(
      screen.getByRole("listitem", { name: "example.org" }),
    ).toHaveTextContent("No open findings.");
  });

  it("shows the score change and a text alternative for the score history", async () => {
    const history = [
      { scan_id: "a", score: 76, scanned_at: "2026-10-18T10:00:00Z" },
      { scan_id: "b", score: 84, scanned_at: "2026-10-18T12:00:00Z" },
    ];
    const rising = {
      sites: [{ ...site, previous_score: 76, score_change: 8, history }],
      fix_first: null,
      other_open: 0,
    };
    mockFetch(route([verified], rising));
    renderApp();
    const card = await screen.findByRole("listitem", { name: "example.org" });
    expect(card).toHaveTextContent("▲ Up 8 since the previous scan");
    expect(
      screen.getByRole("img", {
        name: /Score history over 2 scans: 76, 84. Now 84, up from 76./,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: /Score of each completed scan/ }),
    ).toBeInTheDocument();
  });

  it("tells viewers they cannot scan and offers no setup buttons", async () => {
    mockApi(route([], empty), userWith("VIEWER"));
    renderApp();
    expect(await screen.findByText(/cannot start scans/)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Add a site" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Target URL")).not.toBeInTheDocument();
  });

  it("speaks to viewers as clients, not as site owners", async () => {
    mockApi(route([verified], scanned), userWith("VIEWER"));
    renderApp();
    expect(
      await screen.findByText(/sites shared with you/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/for sites you own or are authorized to test/),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "View sites" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Manage sites" }),
    ).not.toBeInTheDocument();
  });

  it("links a just-finished scan to its findings", async () => {
    window.location.hash = "#/?scan=abc123";
    mockFetch(route([verified], scanned));
    renderApp();
    expect(
      await screen.findByRole("link", { name: "Review 1 finding" }),
    ).toHaveAttribute("href", "#/findings?scan=abc123");
  });
});

describe("Navigation menu (narrow screens)", () => {
  it("opens and closes from the Menu button, closes on Escape and returns focus", async () => {
    mockFetch(() => ({ sites: [], fix_first: null, other_open: 0, items: [] }));
    renderApp();
    const user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "rail-menu");
    await user.click(button);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();
  });

  it("closes after a page is chosen", async () => {
    mockFetch(() => ({ sites: [], fix_first: null, other_open: 0, items: [] }));
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Menu" }));
    await user.click(screen.getByRole("link", { name: "Targets" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute(
        "aria-expanded",
        "false",
      ),
    );
  });
});
