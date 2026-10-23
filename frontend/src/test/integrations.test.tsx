import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ApiTokens from "../components/ApiTokens";
import ScoreBadges from "../components/ScoreBadges";
import type { ApiTokenList, Badge } from "../types";

vi.mock("../api", () => ({
  listApiTokens: vi.fn(),
  createApiToken: vi.fn(),
  revokeApiToken: vi.fn(),
  listBadges: vi.fn(),
  setBadge: vi.fn(),
}));
import * as api from "../api";

const tokens = (extra: Partial<ApiTokenList> = {}): ApiTokenList => ({
  available: true,
  limit: 5,
  items: [],
  ...extra,
});
const badge = (extra: Partial<Badge> = {}): Badge => ({
  target_id: "t1",
  hostname: "example.com",
  enabled: false,
  url: null,
  ...extra,
});

beforeEach(() => {
  vi.resetAllMocks();
});

describe("API tokens", () => {
  it("says plainly when the plan does not include them", async () => {
    vi.mocked(api.listApiTokens).mockResolvedValue(
      tokens({ available: false }),
    );
    render(<ApiTokens />);
    expect(await screen.findByText(/does not include API tokens/)).toBeTruthy();
    expect(screen.queryByLabelText("Token name")).toBeNull();
  });

  it("shows a new token once and lists it without the secret", async () => {
    vi.mocked(api.listApiTokens).mockResolvedValue(tokens());
    vi.mocked(api.createApiToken).mockResolvedValue({
      id: "k1",
      name: "GitHub Actions",
      prefix: "ssk_ab12",
      created_at: "2026-10-22T10:00:00Z",
      last_used_at: null,
      created_by_email: "me@example.com",
      token: "ssk_ab12SECRETSECRET",
    });
    render(<ApiTokens />);
    await userEvent.type(
      await screen.findByLabelText("Token name"),
      "GitHub Actions",
    );
    await userEvent.click(screen.getByRole("button", { name: "Create token" }));
    expect(await screen.findByText("ssk_ab12SECRETSECRET")).toBeTruthy();
    expect(screen.getByText("GitHub Actions")).toBeTruthy();
    await userEvent.click(
      screen.getByRole("button", { name: "I have saved it" }),
    );
    expect(screen.queryByText("ssk_ab12SECRETSECRET")).toBeNull();
    expect(screen.getByText(/never used/)).toBeTruthy();
  });

  it("asks before revoking", async () => {
    vi.mocked(api.listApiTokens).mockResolvedValue(
      tokens({
        items: [
          {
            id: "k1",
            name: "CI",
            prefix: "ssk_ab12",
            created_at: "2026-10-22T10:00:00Z",
            last_used_at: null,
            created_by_email: null,
          },
        ],
      }),
    );
    vi.mocked(api.revokeApiToken).mockResolvedValue(undefined);
    render(<ApiTokens />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Revoke" }),
    );
    expect(api.revokeApiToken).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: "Confirm revoking CI" }),
    );
    expect(api.revokeApiToken).toHaveBeenCalledWith("k1");
    expect(await screen.findByText("No token yet.")).toBeTruthy();
  });
});

describe("score badges", () => {
  it("is off by default and warns that a badge is public", async () => {
    vi.mocked(api.listBadges).mockResolvedValue({ items: [badge()] });
    render(<ScoreBadges manage />);
    expect(await screen.findByText("The badge is off.")).toBeTruthy();
    expect(screen.getByText(/it is public/)).toBeTruthy();
  });

  it("switches on and shows the Markdown", async () => {
    vi.mocked(api.listBadges).mockResolvedValue({ items: [badge()] });
    vi.mocked(api.setBadge).mockResolvedValue(
      badge({
        enabled: true,
        url: "https://getsecurescope.com/api/v1/badges/tok.svg",
      }),
    );
    render(<ScoreBadges manage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Switch badge on" }),
    );
    expect(api.setBadge).toHaveBeenCalledWith("t1", true);
    const box = (await screen.findByLabelText("Markdown")) as HTMLInputElement;
    expect(box.value).toBe(
      "[![SecureScope](https://getsecurescope.com/api/v1/badges/tok.svg)](https://getsecurescope.com)",
    );
  });

  it("hides the controls from people who cannot manage sites", async () => {
    vi.mocked(api.listBadges).mockResolvedValue({ items: [badge()] });
    render(<ScoreBadges manage={false} />);
    await screen.findByText("The badge is off.");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
