import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import { parseOAuthError } from "../router";

function stub(providers: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
      if (path === "/auth/me")
        return { ok: false, status: 401, json: async () => ({ detail: "no" }) };
      if (path === "/auth/providers")
        return { ok: true, status: 200, json: async () => providers };
      return { ok: true, status: 200, json: async () => ({}) };
    }),
  );
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

describe("sign in with Google or GitHub", () => {
  it("offers a link per configured provider on the sign-in page", async () => {
    stub({ providers: ["google", "github"] });
    open("#/login");
    const google = await screen.findByRole("link", {
      name: "Continue with Google",
    });
    expect(google).toHaveAttribute("href", "/api/v1/auth/oauth/google/start");
    expect(
      screen.getByRole("link", { name: "Continue with GitHub" }),
    ).toHaveAttribute("href", "/api/v1/auth/oauth/github/start");
    expect(screen.getByText(/signing in creates one/i)).toBeInTheDocument();
    // Each button carries an icon that screen readers skip; the text alone names the action.
    for (const link of [
      google,
      screen.getByRole("link", { name: "Continue with GitHub" }),
    ]) {
      expect(link.querySelector(".provider-icon")).toHaveAttribute(
        "aria-hidden",
        "true",
      );
    }
  });

  it("offers them on the sign-up page too", async () => {
    stub({ providers: ["google"] });
    open("#/register");
    expect(
      await screen.findByRole("link", { name: "Sign up with Google" }),
    ).toHaveAttribute("href", "/api/v1/auth/oauth/google/start");
    expect(screen.queryByRole("link", { name: /github/i })).toBeNull();
  });

  it("shows nothing extra when no provider is configured or the answer is odd", async () => {
    for (const body of [{ providers: [] }, {}, { providers: ["evil", 3] }]) {
      stub(body);
      const view = open("#/login");
      await screen.findByRole("heading", { name: "Sign in" });
      await waitFor(() =>
        expect(
          vi
            .mocked(fetch)
            .mock.calls.some((c) => String(c[0]).endsWith("/auth/providers")),
        ).toBe(true),
      );
      expect(screen.queryByRole("link", { name: /continue with/i })).toBeNull();
      view.unmount();
    }
  });

  it("explains why a sign-in failed, once, and never echoes the URL text", async () => {
    stub({ providers: ["google"] });
    open("#/login?oauth_error=email_unverified");
    expect(
      await screen.findByText(/no verified email address/i),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/login");
  });

  it("ignores an unknown error code instead of printing it", async () => {
    stub({ providers: [] });
    open("#/login?oauth_error=<b>hacked</b>");
    await screen.findByRole("heading", { name: "Sign in" });
    expect(screen.queryByText(/hacked/)).toBeNull();
    expect(parseOAuthError("#/login?oauth_error=nope")).toBeNull();
    expect(parseOAuthError("#/login?oauth_error=cancelled")).toBe("cancelled");
    expect(parseOAuthError("#/login")).toBeNull();
  });

  it("the privacy notice names the providers and the sign-in cookie", async () => {
    stub({ providers: [] });
    open("#/privacy");
    expect(await screen.findByText(/ss_oauth/)).toBeInTheDocument();
    expect(screen.getAllByText(/Google/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/GitHub/).length).toBeGreaterThan(0);
  });
});
