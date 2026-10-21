import { coverage } from "../../overview";
import { buildHash } from "../../router";
import type {
  Overview,
  ScanSummary,
  Severity,
  SitePosture,
  Target,
  TopFinding,
} from "../../types";
import { SEVERITIES } from "../../types";

/**
 * Rules behind the Bento cards. They are plain functions of data the API already returned, so every
 * line shown on the dashboard can be traced to a record. Nothing here estimates or invents anything.
 */

const RANK: Record<Severity, number> = Object.fromEntries(
  SEVERITIES.map((s, i) => [s, i]),
) as Record<Severity, number>;

/** The site with the lowest score. Ties keep the first one. Sites without a score are ignored. */
export function weakestSite(sites: readonly SitePosture[]): SitePosture | null {
  let best: SitePosture | null = null;
  for (const site of sites) {
    if (site.score === null) continue;
    if (best === null || site.score < (best.score ?? 101)) best = site;
  }
  return best;
}

/** Each site's top open finding, most severe first, then by host name. */
export function topIssues(
  sites: readonly SitePosture[],
  limit = 5,
): TopFinding[] {
  return sites
    .map((s) => s.top_finding)
    .filter((f): f is TopFinding => f !== null)
    .sort(
      (a, b) =>
        RANK[a.severity] - RANK[b.severity] || a.host.localeCompare(b.host),
    )
    .slice(0, limit);
}

export interface PriorityAction {
  id: string;
  label: string;
  detail: string;
  href: string;
}

/** Hosts with a completed scan on record, or `null` when the server did not say (an older server). */
export function scannedHostSet(overview: Overview): ReadonlySet<string> | null {
  return overview.scanned_hosts ? new Set(overview.scanned_hosts) : null;
}

/**
 * What is known about a host's scans. The overview lists only the most recently scanned sites, so not
 * being listed is not proof of anything: `never` needs the server's full list, otherwise it is `unknown`.
 */
export type ScanRecord = "listed" | "unlisted" | "never" | "unknown";

export function scanRecord(
  host: string,
  sites: readonly SitePosture[],
  scanned: ReadonlySet<string> | null,
): ScanRecord {
  if (sites.some((s) => s.host === host)) return "listed";
  if (scanned === null) return "unknown";
  return scanned.has(host) ? "unlisted" : "never";
}

/** Who the score card is about, saying so when it compares only some of the sites. */
export function scoreScope(overview: Overview): string {
  const { listed, total, partial } = coverage(overview);
  if (partial)
    return `Lowest score among the ${listed} most recently scanned sites (${total} scanned)`;
  if (listed > 1)
    return total === null
      ? "Lowest-scoring site listed"
      : "Lowest-scoring site";
  return "Your site";
}

export interface ActionInput {
  targets: readonly Target[];
  sites: readonly SitePosture[];
  /** From `scannedHostSet`. `null` when unknown: the "never scanned" rule is then skipped. */
  scannedHosts: ReadonlySet<string> | null;
  /** Recent scans, newest first. `null` when they could not be loaded: the scan rules are then skipped. */
  scans: readonly ScanSummary[] | null;
  canManage: boolean;
  canRun: boolean;
}

/** Deterministic, ordered rules. The first rules are the ones that block everything after them. */
export function priorityActions(
  input: ActionInput,
  limit = 5,
): PriorityAction[] {
  const { targets, sites, scannedHosts, scans, canManage, canRun } = input;
  const out: PriorityAction[] = [];

  if (canManage) {
    for (const t of targets) {
      if (t.status === "pending")
        out.push({
          id: `verify-${t.id}`,
          label: `Verify ${t.hostname}`,
          detail: "Ownership is not proven yet, so it cannot be scanned.",
          href: "#/targets",
        });
      else if (t.status === "expired" || t.status === "reverify")
        out.push({
          id: `reverify-${t.id}`,
          label: `Re-verify ${t.hostname}`,
          detail: "The ownership check has lapsed. Verify again to scan it.",
          href: "#/targets",
        });
    }
  }

  if (scans) {
    const seen = new Set<string>();
    const newestFirst = [...scans].sort((a, b) =>
      b.created_at.localeCompare(a.created_at),
    );
    for (const scan of newestFirst) {
      if (seen.has(scan.host)) continue;
      seen.add(scan.host);
      if (scan.status === "failed")
        out.push({
          id: `failed-${scan.id}`,
          label: `Investigate the failed scan of ${scan.host}`,
          detail: "Its latest scan did not complete.",
          href: buildHash("history", scan.id),
        });
    }
  }

  for (const site of sites) {
    const urgent =
      (site.open_counts.critical ?? 0) + (site.open_counts.high ?? 0);
    if (urgent > 0)
      out.push({
        id: `urgent-${site.host}`,
        label: `Review ${urgent} critical or high finding${urgent === 1 ? "" : "s"} on ${site.host}`,
        detail: "Open findings with the highest severity.",
        href: buildHash("findings", site.latest_scan_id),
      });
  }

  // Only when the server's full list says so: missing from the capped site list proves nothing.
  if (canRun && scannedHosts) {
    for (const t of targets)
      if (t.status === "verified" && !scannedHosts.has(t.hostname))
        out.push({
          id: `scan-${t.id}`,
          label: `Run a scan of ${t.hostname}`,
          detail: "Verified, with no completed scan on record.",
          href: buildHash("overview", null),
        });
  }

  return out.slice(0, limit);
}

/** The scan's outcome in words, from fields the scan list already carries. */
export function scanOutcome(scan: ScanSummary): string {
  switch (scan.status) {
    case "completed": {
      const n = Object.values(scan.counts).reduce((a, b) => a + (b ?? 0), 0);
      const score = scan.score === null ? "no score" : `score ${scan.score}`;
      return `${score}, ${n} finding${n === 1 ? "" : "s"}`;
    }
    case "failed":
      return "Did not complete";
    case "cancelled":
      return "Cancelled";
    default:
      return "In progress";
  }
}
