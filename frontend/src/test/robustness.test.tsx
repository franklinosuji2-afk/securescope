import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";
import ErrorBoundary from "../components/ErrorBoundary";

function Boom(): never {
  throw new Error("secret internal detail");
}

describe("error boundary", () => {
  beforeEach(() => {
    // React and the boundary both log the caught error; keep the test output clean.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a fixed message instead of a blank screen and never shows the error text", () => {
    render(
      <ErrorBoundary scope="page">
        <Boom />
      </ErrorBoundary>,
    );
    const alert = screen.getByRole("alert");
    expect(within(alert).getByRole("heading").textContent).toBe(
      "This page could not be shown",
    );
    expect(document.body.textContent).not.toContain("secret internal detail");
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "go to the start page" }),
    ).toBeTruthy();
  });

  it("renders its children when nothing fails", () => {
    render(
      <ErrorBoundary scope="page">
        <p>All fine</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("All fine")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("the app-wide version is a main landmark so the page is never empty", () => {
    render(
      <ErrorBoundary scope="app">
        <Boom />
      </ErrorBoundary>,
    );
    expect(within(screen.getByRole("main")).getByRole("alert")).toBeTruthy();
  });

  it("is reset by changing its key, as the router does when the page changes", () => {
    const { rerender } = render(
      <ErrorBoundary scope="page" key="team">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    rerender(
      <ErrorBoundary scope="page" key="targets">
        <p>Targets</p>
      </ErrorBoundary>,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Targets")).toBeTruthy();
  });
});

describe("app shell", () => {
  const user = {
    id: "u1",
    email: "a@example.org",
    email_verified: true,
    organizations: [{ id: "o1", name: "Org", slug: "org", role: "OWNER" }],
  };
  function stub(signedIn: boolean, answers: Record<string, unknown> = {}) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = url.replace(/^\/api\/v1/, "").split("?")[0]!;
        if (path === "/auth/me")
          return signedIn
            ? { ok: true, status: 200, json: async () => user }
            : { ok: false, status: 401, json: async () => ({ detail: "no" }) };
        if (path in answers)
          return { ok: true, status: 200, json: async () => answers[path] };
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [], total: 0 }),
        };
      }),
    );
  }
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.location.hash = "";
  });

  it("the sign-in-required screen is inside the main landmark", async () => {
    stub(false);
    window.location.hash = "#/team";
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    const main = await screen.findByRole("main");
    expect(
      within(main).getByRole("heading", { name: "Sign in required" }),
    ).toBeTruthy();
  });

  it("a page that cannot draw its data shows the message and keeps the menu", async () => {
    // The members list is missing from this answer, which used to blank the whole app.
    stub(true, { "/organizations/o1": { id: "o1", name: "Org" } });
    window.location.hash = "#/team";
    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "This page could not be shown",
      }),
    ).toBeTruthy();
    expect(
      screen.getAllByRole("link", { name: "Targets" }).length,
    ).toBeGreaterThan(0);
  });
});
