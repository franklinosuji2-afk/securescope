import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WebhookAlerts from "../components/WebhookAlerts";
import type { Webhook, WebhookList } from "../types";

vi.mock("../api", () => ({
  listWebhooks: vi.fn(),
  createWebhook: vi.fn(),
  testWebhook: vi.fn(),
  renewWebhookSecret: vi.fn(),
  setWebhookEnabled: vi.fn(),
  deleteWebhook: vi.fn(),
  listWebhookDeliveries: vi.fn(),
}));
import * as api from "../api";

const hook = (extra: Partial<Webhook> = {}): Webhook => ({
  id: "w1",
  address: "https://hooks.example.com/…",
  enabled: true,
  last_attempt_at: null,
  last_status: null,
  consecutive_failures: 0,
  created_at: "2026-10-22T10:00:00Z",
  ...extra,
});
const list = (extra: Partial<WebhookList> = {}): WebhookList => ({
  available: true,
  configured: true,
  limit: 3,
  items: [],
  ...extra,
});

beforeEach(() => {
  vi.resetAllMocks();
});

describe("webhook alerts", () => {
  it("says plainly when the plan does not include them", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ available: false }));
    render(<WebhookAlerts manage />);
    expect(
      await screen.findByText(/Professional and Agency plans/),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Webhook address")).toBeNull();
  });

  it("says when the server has not switched them on", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ configured: false }));
    render(<WebhookAlerts manage />);
    expect(
      await screen.findByText(/not switched on for this server/),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Webhook address")).toBeNull();
  });

  it("shows the signing secret once after adding an address", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list());
    vi.mocked(api.createWebhook).mockResolvedValue({
      ...hook(),
      signing_secret: "whsec_abc123",
    });
    render(<WebhookAlerts manage />);
    await userEvent.type(
      await screen.findByLabelText("Webhook address"),
      "https://hooks.example.com/secret-token",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Add webhook address" }),
    );
    expect(await screen.findByText("whsec_abc123")).toBeTruthy();
    expect(screen.getByText("https://hooks.example.com/…")).toBeTruthy();
    expect(screen.queryByText(/secret-token/)).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: "I have saved it" }),
    );
    expect(screen.queryByText("whsec_abc123")).toBeNull();
  });

  it("shows why an address could not be added", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list());
    vi.mocked(api.createWebhook).mockRejectedValue(
      new Error("The address must start with https://."),
    );
    render(<WebhookAlerts manage />);
    await userEvent.type(
      await screen.findByLabelText("Webhook address"),
      "http://example.com/x",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Add webhook address" }),
    );
    expect(await screen.findByText(/must start with https/)).toBeTruthy();
  });

  it("reports the result of a test message", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ items: [hook()] }));
    vi.mocked(api.testWebhook).mockResolvedValue({
      ok: false,
      status: "Failed (HTTP 503).",
    });
    render(<WebhookAlerts manage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Send test message" }),
    );
    expect(await screen.findByText(/Test message failed/)).toBeTruthy();
  });

  it("explains an endpoint that was switched off after failures", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(
      list({ items: [hook({ enabled: false, consecutive_failures: 10 })] }),
    );
    render(<WebhookAlerts manage />);
    expect(
      await screen.findByText(/Switched off after 10 failed deliveries/),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Switch on" })).toBeTruthy();
  });

  it("asks twice before removing an address", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ items: [hook()] }));
    vi.mocked(api.deleteWebhook).mockResolvedValue(undefined);
    render(<WebhookAlerts manage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Remove" }),
    );
    expect(api.deleteWebhook).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: /Confirm removal/ }),
    );
    await waitFor(() => expect(api.deleteWebhook).toHaveBeenCalledWith("w1"));
    await waitFor(() =>
      expect(screen.queryByText("https://hooks.example.com/…")).toBeNull(),
    );
  });

  it("lets people who cannot manage sites read but not change", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ items: [hook()] }));
    render(<WebhookAlerts manage={false} />);
    expect(await screen.findByText("https://hooks.example.com/…")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
    expect(screen.queryByLabelText("Webhook address")).toBeNull();
  });

  it("lists the recent deliveries of an address when opened", async () => {
    vi.mocked(api.listWebhooks).mockResolvedValue(list({ items: [hook()] }));
    vi.mocked(api.listWebhookDeliveries).mockResolvedValue([
      {
        delivery_id: "d1",
        event: "scan.alert",
        ok: false,
        status: "Failed (HTTP 500).",
        attempts: 2,
        created_at: "2026-10-24T10:00:00Z",
      },
    ]);
    render(<WebhookAlerts manage />);
    await userEvent.click(await screen.findByText("Recent deliveries"));
    expect(await screen.findByText(/Failed \(HTTP 500\)\./)).toBeTruthy();
    expect(screen.getByText(/Scan alert/)).toBeTruthy();
    expect(screen.getByText(/2 attempts/)).toBeTruthy();
    expect(api.listWebhookDeliveries).toHaveBeenCalledWith("w1");
  });
});
