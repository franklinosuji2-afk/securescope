import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import FindingList from "../components/FindingList";
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
function mockApi(handler: Handler, me: User | null = userWith("OWNER"), status = 200): Mock {
  const mock: Mock = { calls: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      mock.calls.push({ url, init });
      if (url.endsWith("/auth/me")) {
        return me
          ? { ok: true, status: 200, json: async () => me }
          : { ok: false, status: 401, json: async () => ({ detail: "Authentication required." }) };
      }
      return { ok: status < 400, status, json: async () => handler(url, init) };
    }),
  );
  return mock;
}

function mockFetch(handler: Handler, status = 200) {
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
    expect(parseHash("#/findings?scan=abc123")).toEqual({ page: "findings", scanId: "abc123", token: null });
    expect(parseHash("#/findings?scan=../x")).toEqual({ page: "findings", scanId: null, token: null });
    expect(parseHash("")).toEqual({ page: "overview", scanId: null, token: null });
    expect(buildHash("history", null)).toBe("#/history");
  });
});

describe("Overview", () => {
  it("shows an honest empty state and no fabricated results", async () => {
    mockFetch(() => ({}));
    renderApp();
    expect(await screen.findByText("No scan yet")).toBeInTheDocument();
    expect(screen.queryByText(/Heuristic score/)).not.toBeInTheDocument();
  });

  it("keeps Start disabled until authorization is acknowledged", async () => {
    mockFetch(() => ({}));
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Target URL"), "https://example.org");
    const button = screen.getByRole("button", { name: "Start scan" });
    expect(button).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
  });

  it("shows the server error when a target is rejected", async () => {
    mockFetch(() => ({ detail: "Target resolves to a private address." }), 422);
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Target URL"), "http://internal.test");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("private address");
  });

  it("renders a completed scan loaded from the URL", async () => {
    window.location.hash = "#/?scan=abc123";
    mockFetch(() => scan);
    renderApp();
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
    renderApp();
    await waitFor(() => expect(screen.getByText("example.org")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Open scan of example.org" })).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    window.location.hash = "#/history";
    mockFetch(() => ({ items: [], total: 0 }));
    renderApp();
    expect(await screen.findByText("No scans yet")).toBeInTheDocument();
  });
});


describe("Authentication", () => {
  it("shows the sign-in page when there is no session", async () => {
    mockApi(() => ({}), null);
    renderApp();
    expect(await screen.findByRole("heading", { name: "Sign in required" })).toBeInTheDocument();
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
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
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
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({ email: "alice@example.org" });
  });

  it("sends the CSRF header and organization header on state-changing requests", async () => {
    document.cookie = "ss_csrf=csrf-token-value";
    const mock = mockFetch(() => ({}), 202);
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Target URL"), "https://example.org");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    await waitFor(() => expect(mock.calls.some((c) => c.url.endsWith("/scans") && c.init?.method === "POST")).toBe(true));
    const call = mock.calls.find((c) => c.url.endsWith("/scans") && c.init?.method === "POST");
    const headers = call?.init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("csrf-token-value");
    expect(headers["X-Organization-Id"]).toBe("org1");
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
    await waitFor(() => expect(mock.calls.some((c) => c.url.endsWith("/auth/logout"))).toBe(true));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("Team", () => {
  const detail = {
    ...userWith("OWNER").organizations[0],
    members: [
      { user_id: "u1", email: "alice@example.org", role: "OWNER", joined_at: "2026-10-18T10:00:00Z" },
      { user_id: "u2", email: "bob@example.org", role: "VIEWER", joined_at: "2026-10-18T11:00:00Z" },
    ],
  };

  it("lets owners manage members", async () => {
    window.location.hash = "#/team";
    mockApi(() => detail, userWith("OWNER"));
    renderApp();
    expect(await screen.findByText("bob@example.org")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove bob@example.org" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Add a member" })).toBeInTheDocument();
  });

  it("is read-only for members", async () => {
    window.location.hash = "#/team";
    mockApi(() => detail, userWith("MEMBER"));
    renderApp();
    expect(await screen.findByText("bob@example.org")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Add a member" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove bob@example.org" })).not.toBeInTheDocument();
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

describe("Targets", () => {
  it("shows exact DNS and file instructions for an unverified domain", async () => {
    window.location.hash = "#/targets";
    mockFetch(() => ({ items: [targetBase] }));
    renderApp();
    expect(await screen.findByText("_securescope-challenge.example.org")).toBeInTheDocument();
    // The same value is shown for the DNS record and for the file content.
    expect(screen.getAllByText("securescope-verification=" + "a".repeat(32), { selector: "dd code" })).toHaveLength(2);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify DNS record" })).toBeEnabled();
  });

  it("shows the server's reason when verification fails and never claims success", async () => {
    window.location.hash = "#/targets";
    // Like the real server, the list returned after a failed check carries the reason.
    let current = targetBase;
    const mock = mockFetch((url) => {
      if (url.endsWith("/verify")) {
        current = { ...targetBase, last_check_error: "No TXT record was found at _securescope-challenge.example.org." };
        return current;
      }
      return { items: [current] };
    });
    renderApp();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Verify DNS record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No TXT record was found");
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
    await user.click(screen.getByRole("button", { name: /Confirm removal of example.org/ }));
    await waitFor(() => expect(mock.calls.some((c) => c.init?.method === "DELETE")).toBe(true));
  });

  it("hides management controls from viewers", async () => {
    window.location.hash = "#/targets";
    mockApi(() => ({ items: [{ ...targetBase, status: "verified", verified_at: "2026-10-18T11:00:00Z", verification_method: "dns_txt" }] }), userWith("VIEWER"));
    renderApp();
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Domain name")).not.toBeInTheDocument();
  });

  it("points to Targets when a scan is refused because ownership is unverified", async () => {
    mockFetch(() => ({ detail: "Ownership of example.org has not been verified. Add and verify it under Targets first." }), 403);
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Target URL"), "https://example.org");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Start scan" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("has not been verified");
    expect(screen.getByRole("link", { name: "Go to Targets" })).toHaveAttribute("href", "#/targets");
  });
});
