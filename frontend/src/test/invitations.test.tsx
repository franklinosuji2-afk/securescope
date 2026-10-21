import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { forgetInvite, pendingInvite } from "../pendingInvite";
import { parseHash } from "../router";
import type { Invitation, Role, User } from "../types";

const TOKEN = "T".repeat(43);

function me(email: string, role: Role = "OWNER"): User {
  return {
    id: "u1",
    email,
    email_verified: true,
    organizations: [{ id: "org1", name: "Alice Org", slug: "alice-org", role }],
  };
}

interface Call {
  url: string;
  init?: RequestInit;
}

function stub(options: {
  user: User | null;
  preview?: unknown;
  previewStatus?: number;
  acceptStatus?: number;
  acceptBody?: unknown;
  pending?: Invitation[];
}) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
      const reply = (status: number, body: unknown) => ({
        ok: status < 400,
        status,
        json: async () => body,
      });
      if (path === "/auth/me")
        return options.user
          ? reply(200, options.user)
          : reply(401, { detail: "Authentication required." });
      if (path === "/auth/providers") return reply(200, { providers: [] });
      if (path === "/invitations/preview")
        return reply(
          options.previewStatus ?? 200,
          options.preview ?? {
            organization_name: "Alice Org",
            email: "client@example.com",
            role: "VIEWER",
          },
        );
      if (path === "/invitations/accept")
        return reply(
          options.acceptStatus ?? 200,
          options.acceptBody ?? { organization_id: "org1" },
        );
      if (path === "/organizations/org1/invitations") {
        if (init?.method === "POST")
          return reply(201, {
            id: "i2",
            email: "new@example.com",
            role: "VIEWER",
            invited_by_email: "alice@example.com",
            created_at: "2026-10-21T10:00:00Z",
            expires_at: "2026-10-28T10:00:00Z",
          });
        return reply(200, options.pending ?? []);
      }
      if (path === "/organizations/org1")
        return reply(200, {
          ...(options.user?.organizations[0] ?? {}),
          members: [
            {
              user_id: "u1",
              email: "alice@example.com",
              role: "OWNER",
              joined_at: "2026-10-18T10:00:00Z",
            },
          ],
        });
      return reply(200, {});
    }),
  );
  return calls;
}

function open(hash: string) {
  window.location.hash = hash;
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
  forgetInvite();
});

describe("invitation links", () => {
  it("are routed as public pages and carry the token", () => {
    expect(parseHash(`#/accept-invite?token=${TOKEN}`)).toMatchObject({
      page: "accept-invite",
      token: TOKEN,
    });
  });

  it("show what they are for and ask a signed-out visitor to sign in with the invited address", async () => {
    stub({ user: null });
    open(`#/accept-invite?token=${TOKEN}`);
    expect(await screen.findByText("Alice Org")).toBeInTheDocument();
    expect(screen.getByText(/read-only access/)).toBeInTheDocument();
    expect(
      screen.getByText(/only works with that email address/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "#/login",
    );
    expect(
      screen.getByRole("link", { name: "Create an account" }),
    ).toHaveAttribute("href", "#/register");
    // The link survives the sign-in, which may leave the site and come back.
    await waitFor(() => expect(pendingInvite()).toBe(TOKEN));
  });

  it("takes a person back to the invitation after they sign in", async () => {
    stub({ user: me("client@example.com", "VIEWER") });
    window.sessionStorage.setItem("securescope.invite", TOKEN);
    open("#/");
    expect(
      await screen.findByText(/You are invited to join/),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe(`#/accept-invite?token=${TOKEN}`);
    // Taken once, so it cannot trap them on this page.
    expect(pendingInvite()).toBeNull();
  });

  it("lets the right person accept, then selects the workspace", async () => {
    const calls = stub({ user: me("client@example.com", "VIEWER") });
    open(`#/accept-invite?token=${TOKEN}`);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Accept and join" }),
    );
    expect(await screen.findByText(/You joined Alice Org/)).toBeInTheDocument();
    const post = calls.find((c) => c.url.endsWith("/invitations/accept"));
    expect(JSON.parse(String(post?.init?.body))).toEqual({ token: TOKEN });
  });

  it("warns when the signed-in address is not the invited one and offers no accept button", async () => {
    stub({ user: me("someone-else@example.com", "VIEWER") });
    open(`#/accept-invite?token=${TOKEN}`);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "someone-else@example.com",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("client@example.com");
    expect(
      screen.queryByRole("button", { name: "Accept and join" }),
    ).toBeNull();
  });

  it("shows the server's reason when the link is no longer valid", async () => {
    stub({
      user: null,
      previewStatus: 404,
      preview: { detail: "This invitation is no longer valid." },
    });
    open(`#/accept-invite?token=${TOKEN}`);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no longer valid",
    );
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
    expect(pendingInvite()).toBeNull();
  });

  it("says so when the link has no code", async () => {
    stub({ user: null });
    open("#/accept-invite");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "missing its invitation code",
    );
  });
});

describe("inviting from the Team page", () => {
  const pending: Invitation = {
    id: "i1",
    email: "waiting@example.com",
    role: "VIEWER",
    invited_by_email: "alice@example.com",
    created_at: "2026-10-20T10:00:00Z",
    expires_at: "2026-10-27T10:00:00Z",
  };

  it("sends an invitation with the chosen role and confirms it", async () => {
    const calls = stub({ user: me("alice@example.com"), pending: [pending] });
    open("#/team");
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Email to invite"),
      "new@example.com",
    );
    await user.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(
      await screen.findByText("Invitation sent to new@example.com."),
    ).toBeInTheDocument();
    const post = calls.find(
      (c) => c.url.endsWith("/invitations") && c.init?.method === "POST",
    );
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      email: "new@example.com",
      role: "VIEWER",
    });
    expect(screen.getByLabelText("Email to invite")).toHaveValue("");
  });

  it("defaults to Viewer and never offers Owner", async () => {
    stub({ user: me("alice@example.com") });
    open("#/team");
    const select = await screen.findByLabelText("Role");
    expect(select).toHaveValue("VIEWER");
    const options = Array.from(
      (select as HTMLSelectElement).options,
      (o) => o.value,
    );
    expect(options).not.toContain("OWNER");
  });

  it("lists pending invitations and revokes one", async () => {
    const calls = stub({ user: me("alice@example.com"), pending: [pending] });
    open("#/team");
    expect(await screen.findByText("waiting@example.com")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", {
        name: "Revoke invitation for waiting@example.com",
      }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.url.endsWith("/invitations/i1") && c.init?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("shows no invitation controls to members who cannot manage the team", async () => {
    const calls = stub({ user: me("alice@example.com", "MEMBER") });
    open("#/team");
    await screen.findByText("alice@example.com");
    expect(screen.queryByLabelText("Email to invite")).toBeNull();
    expect(calls.some((c) => c.url.endsWith("/invitations"))).toBe(false);
  });
});
