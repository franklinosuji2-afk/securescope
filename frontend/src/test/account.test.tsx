import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import type { User } from "../types";

function me(verified = true): User {
  return {
    id: "u1",
    email: "owner@example.com",
    email_verified: verified,
    organizations: [{ id: "org1", name: "Org", slug: "org", role: "OWNER" }],
  };
}

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function stub(
  user: User,
  handlers: Record<string, { status: number; body?: unknown }> = {},
) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({
        url,
        method,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
      const hit = handlers[`${method} ${path}`];
      const reply = (status: number, body: unknown) => ({
        ok: status < 400,
        status,
        json: async () => body,
      });
      if (hit) return reply(hit.status, hit.body ?? {});
      if (path === "/auth/me") return reply(200, user);
      if (path === "/auth/providers") return reply(200, { providers: [] });
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
});

describe("an account whose email address is not confirmed", () => {
  it("sees how to confirm it instead of the dashboard, and no dashboard data is requested", async () => {
    const calls = stub(me(false));
    open("#/");
    expect(
      await screen.findByRole("heading", {
        name: "Confirm your email address",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    const dashboard = calls.filter((c) =>
      /\/(scans|targets|overview)/.test(c.url),
    );
    expect(dashboard).toEqual([]);
  });

  it("can ask for the email again", async () => {
    const calls = stub(me(false));
    open("#/");
    await userEvent
      .setup()
      .click(
        await screen.findByRole("button", { name: "Send the email again" }),
      );
    expect(await screen.findByText(/Sent\. Open the link/)).toBeInTheDocument();
    expect(
      calls.some(
        (c) =>
          c.method === "POST" && c.url.endsWith("/auth/resend-verification"),
      ),
    ).toBe(true);
  });

  it("is let in once the server says the address is confirmed", async () => {
    stub(me(true));
    open("#/");
    expect(
      await screen.findByRole("navigation", { name: "Primary" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Confirm your email address" }),
    ).toBeNull();
  });
});

describe("the Account page", () => {
  it("is in the menu", async () => {
    stub(me());
    open("#/");
    expect(
      await screen.findByRole("link", { name: "Account" }),
    ).toHaveAttribute("href", "#/account");
  });

  it("changes the password and says so", async () => {
    const calls = stub(me(), { "PATCH /account/password": { status: 204 } });
    open("#/account");
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Current password"),
      "old-password-123",
    );
    await user.type(screen.getByLabelText("New password"), "new-password-456");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(
      await screen.findByText("Your password was changed."),
    ).toBeInTheDocument();
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.body).toEqual({
      current_password: "old-password-123",
      new_password: "new-password-456",
    });
  });

  it("shows the server's reason when the current password is wrong", async () => {
    stub(me(), {
      "PATCH /account/password": {
        status: 400,
        body: { detail: "Your current password is not correct." },
      },
    });
    open("#/account");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Current password"), "nope");
    await user.type(screen.getByLabelText("New password"), "new-password-456");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "current password is not correct",
    );
  });

  it("will not delete the account until DELETE is typed, then deletes and returns to sign-in", async () => {
    const calls = stub(me(), { "DELETE /account": { status: 204 } });
    open("#/account");
    const user = userEvent.setup();
    const button = await screen.findByRole("button", {
      name: "Delete my account",
    });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Your password"), "my-password-123");
    await user.type(screen.getByLabelText("Type DELETE to confirm"), "delete");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText("Type DELETE to confirm"));
    await user.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() => expect(window.location.hash).toBe("#/login"));
    const del = calls.find((c) => c.method === "DELETE");
    expect(del?.body).toEqual({
      password: "my-password-123",
      confirm: "DELETE",
    });
  });

  it("shows why deletion is refused, for example when other people still depend on the workspace", async () => {
    stub(me(), {
      "DELETE /account": {
        status: 409,
        body: { detail: "You are the only owner of Org, which others use." },
      },
    });
    open("#/account");
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Type DELETE to confirm"),
      "DELETE",
    );
    await user.click(screen.getByRole("button", { name: "Delete my account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("only owner");
    expect(window.location.hash).toBe("#/account");
  });
});

const freePlan = {
  plan_id: "free",
  name: "Free",
  price_eur_month: 0,
  limits: {
    websites: 1,
    scans_per_month: 3,
    history_days: 30,
    can_invite: false,
  },
  usage: {
    websites: 1,
    scans_this_period: 2,
    period_start: "2026-10-01T00:00:00Z",
    period_end: "2026-11-01T00:00:00Z",
  },
};

describe("the plan", () => {
  it("shows an owner what the plan includes and how much is used", async () => {
    stub(me(), {
      "GET /organizations/org1/plan": { status: 200, body: freePlan },
    });
    open("#/account");
    expect(
      await screen.findByRole("heading", { name: "Your plan" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("1 of 1")).toBeInTheDocument();
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
    expect(screen.getByText("30 days")).toBeInTheDocument();
    expect(screen.getByText("Agency plan")).toBeInTheDocument();
  });

  it("is not shown to a client, and nothing is requested for them", async () => {
    const viewer = me();
    viewer.organizations = [
      { id: "org1", name: "Org", slug: "org", role: "VIEWER" },
    ];
    const calls = stub(viewer);
    open("#/account");
    await screen.findByRole("heading", { name: "Change password" });
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
    expect(calls.some((c) => c.url.endsWith("/plan"))).toBe(false);
  });

  it("replaces the invitation form with the Agency message on a plan that cannot invite", async () => {
    stub(me(), {
      "GET /organizations/org1/plan": { status: 200, body: freePlan },
      "GET /organizations/org1": {
        status: 200,
        body: {
          id: "org1",
          name: "Org",
          slug: "org",
          role: "OWNER",
          members: [],
        },
      },
      "GET /organizations/org1/invitations": { status: 200, body: [] },
    });
    open("#/team");
    expect(
      await screen.findByText(/part of the Agency plan/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Send invitation" }),
    ).toBeNull();
  });
});

describe("account settings: details, devices and your data", () => {
  const sessions = [
    {
      id: "s-now",
      created_at: "2026-10-24T10:00:00Z",
      expires_at: "2026-11-24T10:00:00Z",
      current: true,
    },
    {
      id: "s-phone",
      created_at: "2026-10-20T08:00:00Z",
      expires_at: "2026-11-20T08:00:00Z",
      current: false,
    },
  ];

  it("shows the account facts", async () => {
    stub(me(), {
      "GET /account": {
        status: 200,
        body: {
          email: "owner@example.com",
          email_verified: true,
          status: "active",
          created_at: "2026-10-01T09:00:00Z",
          has_password: true,
        },
      },
    });
    open("#/account");
    expect(await screen.findByText(/· verified/)).toBeInTheDocument();
    expect(screen.getByText("Member since")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("lists devices, never offers to sign out this one, and signs out another", async () => {
    const calls = stub(me(), {
      "GET /account/sessions": { status: 200, body: sessions },
      "DELETE /account/sessions/s-phone": { status: 204 },
    });
    open("#/account");
    expect(await screen.findByText("This device")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", {
      name: /^Sign out the device/,
    });
    expect(buttons).toHaveLength(1);
    await userEvent.setup().click(buttons[0]!);
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "DELETE" &&
            c.url.endsWith("/account/sessions/s-phone"),
        ),
      ).toBe(true),
    );
  });

  it("signs out all other devices with one button", async () => {
    const calls = stub(me(), {
      "GET /account/sessions": { status: 200, body: sessions },
      "POST /account/sessions/revoke-others": { status: 204 },
    });
    open("#/account");
    await userEvent.setup().click(
      await screen.findByRole("button", {
        name: "Sign out all other devices",
      }),
    );
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "POST" &&
            c.url.endsWith("/account/sessions/revoke-others"),
        ),
      ).toBe(true),
    );
  });

  it("offers the data download as a plain link to the export", async () => {
    stub(me());
    open("#/account");
    const link = await screen.findByRole("link", {
      name: "Download my data (JSON)",
    });
    expect(link).toHaveAttribute("href", "/api/v1/account/export");
    expect(link).toHaveAttribute("download");
  });
});
