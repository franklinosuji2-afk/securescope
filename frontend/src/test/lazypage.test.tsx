import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PageLoader, lazyPage } from "../lazyPage";

describe("lazily loaded pages", () => {
  it("show the page once its code has loaded", async () => {
    const Page = lazyPage(async () => ({ default: () => <p>Loaded page</p> }));
    render(
      <PageLoader>
        <Page />
      </PageLoader>,
    );
    expect(await screen.findByText("Loaded page")).toBeInTheDocument();
  });

  it("explain a failed load instead of leaving an empty screen", async () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    const Page = lazyPage<() => React.ReactElement>(() =>
      Promise.reject(new Error("Failed to fetch dynamically imported module")),
    );
    render(
      <PageLoader>
        <Page />
      </PageLoader>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "This page could not be loaded",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    quiet.mockRestore();
  });
});
