import {
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ScanActivityList,
  SiteInventoryList,
} from "../components/bento/OverviewLists";
import { useRecentScans } from "../components/bento/useRecentScans";
import type { RecentScans } from "../components/bento/useRecentScans";
import Landing from "../pages/Landing";
import type { ScanSummary, SitePosture, Target } from "../types";

const scan = (
  id: string,
  status: ScanSummary["status"],
  over: Partial<ScanSummary> = {},
): ScanSummary => ({
  id,
  target_url: `https://${id}.test`,
  host: `${id}.test`,
  status,
  score: status === "completed" ? 80 : null,
  grade: null,
  created_at: "2026-10-28T10:00:00Z",
  finished_at: null,
  counts: status === "completed" ? { high: 1, low: 1 } : {},
  ...over,
});

const recent = (over: Partial<RecentScans>): RecentScans => ({
  loading: false,
  error: null,
  items: [],
  retry: () => undefined,
  ...over,
});

const target = (hostname: string, status: Target["status"]): Target => ({
  id: hostname,
  hostname,
  status,
  challenge_token: "a".repeat(32),
  challenge_expires_at: null,
  verified_at: null,
  verification_method: null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: "",
  dns_record_value: "",
  http_file_url: "",
  http_file_content: "",
});

const posture = (host: string, score: number | null): SitePosture => ({
  host,
  latest_scan_id: `scan-${host}`,
  score,
  grade: score === null ? null : "B",
  scanned_at: "2026-10-18T12:00:00Z",
  previous_score: null,
  score_change: null,
  open_counts: {},
  open_total: 2,
  top_finding: null,
  history: [],
});

afterEach(() => vi.restoreAllMocks());

describe("scan activity", () => {
  it("links every scan to its result and names its status in words", () => {
    render(
      <ScanActivityList
        recent={recent({
          items: [
            scan("a", "completed"),
            scan("b", "failed"),
            scan("c", "running"),
            scan("d", "cancelled"),
          ],
        })}
      />,
    );
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "#/history?scan=a",
      "#/history?scan=b",
      "#/history?scan=c",
      "#/history?scan=d",
    ]);
    expect(within(links[0]!).getByText("Completed")).toBeInTheDocument();
    expect(
      within(links[0]!).getByText("score 80, 2 findings"),
    ).toBeInTheDocument();
    expect(within(links[1]!).getByText("Failed")).toBeInTheDocument();
    expect(within(links[1]!).getByText("Did not complete")).toBeInTheDocument();
    expect(within(links[2]!).getByText("In progress")).toBeInTheDocument();
    // The outcome line and the status pill both say it.
    expect(within(links[3]!).getAllByText("Cancelled")).toHaveLength(2);
  });

  it("says it is loading, and hides the placeholder rows from assistive technology", () => {
    const { container } = render(
      <ScanActivityList recent={recent({ loading: true })} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading scans");
    expect(container.querySelector(".act-skeleton")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("shows the problem with a way to try again", async () => {
    const retry = vi.fn();
    render(
      <ScanActivityList
        recent={recent({ error: "Could not load scans.", retry })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load scans.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("explains an empty list", () => {
    render(<ScanActivityList recent={recent({})} />);
    expect(screen.getByText("No scans yet.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("loading scans again", () => {
  it("loads the list again after a failure when asked", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Could not load scans." }),
      })
      .mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ items: [scan("a", "completed")], total: 1 }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useRecentScans("k"));
    await waitFor(() => expect(result.current.error).not.toBeNull());
    result.current.retry();
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });
});

describe("site inventory", () => {
  const none = () => "no completed scan on record";

  it("summarises ownership and keeps the wording of each row", () => {
    const targets = [
      target("a.test", "verified"),
      target("b.test", "verified"),
      target("c.test", "pending"),
      target("d.test", "expired"),
    ];
    render(
      <SiteInventoryList
        targets={targets}
        siteByHost={new Map([["a.test", posture("a.test", 90)]])}
        describe={none}
        canManage
      />,
    );
    expect(
      screen.getByText("4 sites, 2 verified, 2 to verify"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ownership verified · score 90, 2 open/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Ownership not verified yet · no completed scan on record/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Verification expired · no completed scan on record/),
    ).toBeInTheDocument();
  });

  it("shows the score once to assistive technology, not twice", () => {
    const { container } = render(
      <SiteInventoryList
        targets={[target("a.test", "verified")]}
        siteByHost={new Map([["a.test", posture("a.test", 90)]])}
        describe={none}
        canManage
      />,
    );
    expect(container.querySelector(".inv-score")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(container.querySelector(".inv-mark")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("shows no score for a site that has none", () => {
    const { container } = render(
      <SiteInventoryList
        targets={[target("a.test", "verified")]}
        siteByHost={new Map([["a.test", posture("a.test", null)]])}
        describe={none}
        canManage
      />,
    );
    expect(container.querySelector(".inv-score")).toBeNull();
    expect(screen.getByText(/score –, 2 open/)).toBeInTheDocument();
  });

  it("lists six sites at most", () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      target(`s${i}.test`, "verified"),
    );
    const { container } = render(
      <SiteInventoryList
        targets={many}
        siteByHost={new Map()}
        describe={none}
        canManage
      />,
    );
    expect(container.querySelectorAll(".inv-item")).toHaveLength(6);
    expect(screen.getByText("9 sites, 9 verified")).toBeInTheDocument();
    expect(screen.getByText("Showing 6 of 9 sites.")).toBeInTheDocument();
  });

  it("tells people who can manage sites what to do, and others what to expect", () => {
    const { rerender } = render(
      <SiteInventoryList
        targets={[]}
        siteByHost={new Map()}
        describe={none}
        canManage
      />,
    );
    expect(screen.getByText("No sites added yet.")).toBeInTheDocument();
    expect(screen.getByText(/Add a site you own/)).toBeInTheDocument();
    rerender(
      <SiteInventoryList
        targets={[]}
        siteByHost={new Map()}
        describe={none}
        canManage={false}
      />,
    );
    expect(screen.queryByText(/Add a site you own/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/once someone with access adds them/),
    ).toBeInTheDocument();
  });
});

describe("questions on the home page", () => {
  it("groups every question and keeps each answer reachable", () => {
    const { container } = render(<Landing />);
    const groups = container.querySelectorAll(".faq-group");
    expect(groups).toHaveLength(3);
    expect([...groups].map((g) => g.querySelector("h3")?.textContent)).toEqual([
      "About SecureScope",
      "Safety and permission",
      "Monitoring and your data",
    ]);
    const questions = [...container.querySelectorAll(".faq-group summary")];
    expect(questions).toHaveLength(7);
    for (const q of questions)
      expect(
        q.parentElement?.querySelector("p")?.textContent?.length,
      ).toBeGreaterThan(20);
  });
});
