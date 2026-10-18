import type { Finding, ScanDetail, ScanSummary, Severity, Target } from "./types";
import { SEVERITIES } from "./types";

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

export function hasCompletedScan(scans: readonly ScanSummary[]): boolean {
  return scans.some((s) => s.status === "completed");
}

/** The four steps of getting to a first useful result. The first unfinished step is the current one. */
export function setupSteps(targets: readonly Target[], scans: readonly ScanSummary[], canManage: boolean): SetupStep[] {
  const added = targets.length > 0;
  const pending = targets.find((t) => t.status !== "verified");
  const verified = targets.some((t) => t.status === "verified");
  const scanned = scans.length > 0;
  const done = [added, verified, scanned, false];

  const steps: SetupStep[] = [
    {
      id: "add",
      title: "Add the site you want to check",
      detail: "Enter the domain name. You can only scan sites you own or are allowed to test.",
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
      action: canManage && added ? { label: pending ? `Verify ${pending.hostname}` : "Open targets", href: "#/targets" } : null,
    },
    {
      id: "scan",
      title: "Run your first scan",
      detail: "Choose a verified site below. A scan is one page load plus same-site redirects and takes a few seconds.",
      state: "waiting",
      action: null,
    },
    {
      id: "review",
      title: "Read what it found",
      detail: "Every finding explains the risk, shows the evidence and says what to change.",
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

export interface SiteSummary {
  host: string;
  latest: ScanSummary;
  previous: ScanSummary | null;
  /** Score change since the previous completed scan of the same host; null when there is no earlier scan. */
  delta: number | null;
  verified: boolean;
}

/** One entry per host that has a completed scan, newest first. */
export function siteSummaries(targets: readonly Target[], scans: readonly ScanSummary[], limit = 6): SiteSummary[] {
  const completed = scans
    .filter((s) => s.status === "completed")
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const byHost = new Map<string, ScanSummary[]>();
  for (const scan of completed) byHost.set(scan.host, [...(byHost.get(scan.host) ?? []), scan]);
  const verifiedHosts = new Set(targets.filter((t) => t.status === "verified").map((t) => t.hostname.toLowerCase()));
  const out: SiteSummary[] = [];
  for (const [host, list] of byHost) {
    const latest = list[0]!;
    const previous = list[1] ?? null;
    const delta = previous && latest.score != null && previous.score != null ? latest.score - previous.score : null;
    out.push({ host, latest, previous, delta, verified: verifiedHosts.has(host.toLowerCase()) });
  }
  return out.slice(0, limit);
}

export function openFindings(findings: readonly Finding[]): Finding[] {
  return findings.filter((f) => f.status === "open");
}

export function openCounts(findings: readonly Finding[]): Partial<Record<Severity, number>> {
  const counts: Partial<Record<Severity, number>> = {};
  for (const f of openFindings(findings)) counts[f.severity] = (counts[f.severity] ?? 0) + 1;
  return counts;
}

export function totalOf(counts: Partial<Record<Severity, number>>): number {
  return SEVERITIES.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
}

export interface FixFirst {
  scan: ScanDetail;
  finding: Finding;
  /** How many other open findings across the sites shown. */
  others: number;
}

const CONFIDENCE_RANK = { high: 0, medium: 1, low: 2 } as const;

/** The single open finding most worth fixing next: highest severity, then most certain. */
export function fixFirst(details: readonly ScanDetail[]): FixFirst | null {
  const all = details.flatMap((scan) => openFindings(scan.findings).map((finding) => ({ scan, finding })));
  if (all.length === 0) return null;
  all.sort(
    (a, b) =>
      SEVERITIES.indexOf(a.finding.severity) - SEVERITIES.indexOf(b.finding.severity) ||
      CONFIDENCE_RANK[a.finding.confidence] - CONFIDENCE_RANK[b.finding.confidence] ||
      a.finding.id.localeCompare(b.finding.id),
  );
  const first = all[0]!;
  return { scan: first.scan, finding: first.finding, others: all.length - 1 };
}

export function deltaText(delta: number | null): string {
  if (delta === null) return "First scan of this site";
  if (delta === 0) return "No change since the previous scan";
  return `${delta > 0 ? "▲ Up" : "▼ Down"} ${Math.abs(delta)} since the previous scan`;
}
