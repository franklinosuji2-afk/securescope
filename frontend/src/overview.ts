import type { Overview, Target } from "./types";

/** Pure logic behind the Overview page, kept apart from React so it can be tested directly. */

export type StepState = "done" | "current" | "waiting";
export type StepId = "add" | "verify" | "scan" | "review";

export interface SetupStep {
  id: StepId;
  title: string;
  detail: string;
  state: StepState;
  action: { label: string; href: string } | null;
}

/** The four steps of getting to a first useful result. The first unfinished step is the current one. */
export function setupSteps(
  targets: readonly Target[],
  scanned: boolean,
  canManage: boolean,
): SetupStep[] {
  const added = targets.length > 0;
  const pending = targets.find((t) => t.status !== "verified");
  const verified = targets.some((t) => t.status === "verified");
  const done = [added, verified, scanned, false];

  const steps: SetupStep[] = [
    {
      id: "add",
      title: "Add the site you want to check",
      detail:
        "Enter the domain name. You can only scan sites you own or are allowed to test.",
      state: "waiting",
      action: canManage ? { label: "Add a site", href: "#/targets" } : null,
    },
    {
      id: "verify",
      title: "Prove you control it",
      detail: pending
        ? `Publish a DNS record or a small file for ${pending.hostname}, then press verify. This keeps SecureScope from being used on other people's sites.`
        : "Publish a DNS record or a small file, then press verify. This keeps SecureScope from being used on other people's sites.",
      state: "waiting",
      action:
        canManage && added
          ? {
              label: pending ? `Verify ${pending.hostname}` : "Open targets",
              href: "#/targets",
            }
          : null,
    },
    {
      id: "scan",
      title: "Run your first scan",
      detail:
        "Choose a verified site below. A scan is one page load plus same-site redirects and takes a few seconds.",
      state: "waiting",
      action: null,
    },
    {
      id: "review",
      title: "Read what it found",
      detail:
        "Every finding explains the risk, shows the evidence and says what to change.",
      state: "waiting",
      action: null,
    },
  ];
  let currentSet = false;
  steps.forEach((step, i) => {
    if (done[i]) step.state = "done";
    else if (!currentSet) {
      step.state = "current";
      currentSet = true;
    }
  });
  return steps;
}

export interface Coverage {
  /** Sites the overview lists; the server caps this. */
  listed: number;
  /** Hosts with a completed scan on record, or null when the server did not say. */
  total: number | null;
  /** True only when it is known that some scanned sites are not listed. */
  partial: boolean;
}

/** How much of the organization the listed sites cover, so totals and comparisons can say so. */
export function coverage(overview: Overview): Coverage {
  const listed = overview.sites.length;
  const total = overview.scanned_hosts ? overview.scanned_hosts.length : null;
  return { listed, total, partial: total !== null && total > listed };
}

export function deltaText(delta: number | null): string {
  if (delta === null) return "First scan of this site";
  if (delta === 0) return "No change since the previous scan";
  return `${delta > 0 ? "▲ Up" : "▼ Down"} ${Math.abs(delta)} since the previous scan`;
}

export interface ChartPoint {
  x: number;
  y: number;
}

/** Maps scores (0 to 100, fixed scale so a drop looks like a drop) onto a width x height box with padding. */
export function chartPoints(
  scores: readonly number[],
  width: number,
  height: number,
  pad = 4,
): ChartPoint[] {
  const n = scores.length;
  return scores.map((score, i) => ({
    x: n === 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (n - 1),
    y:
      pad +
      ((100 - Math.min(100, Math.max(0, score))) * (height - 2 * pad)) / 100,
  }));
}

/** Plain-language summary of a score history, used as the chart's text alternative. */
export function historySummary(scores: readonly number[]): string {
  if (scores.length === 0) return "No score history yet.";
  if (scores.length === 1) return `One scan so far, score ${scores[0]}.`;
  const first = scores[0]!;
  const last = scores[scores.length - 1]!;
  const trend =
    last > first
      ? `up from ${first}`
      : last < first
        ? `down from ${first}`
        : `unchanged from ${first}`;
  return `Score history over ${scores.length} scans: ${scores.join(", ")}. Now ${last}, ${trend}.`;
}
