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
