import { useEffect, useState } from "react";
import { appScanningAvailable, type AppUsage } from "./api";

/** Whether App Scanning is switched on for this deployment (null while unknown). The server decides, and
 * answers 404 for everything while the feature is off; this only decides whether to show the menu entry. */
export function useAppScanningAvailable(
  organizationId: string | null,
  allowed: boolean,
): boolean | null {
  const [state, setState] = useState<{ org: string; value: boolean } | null>(
    null,
  );
  useEffect(() => {
    if (!organizationId || !allowed) return;
    let live = true;
    void appScanningAvailable().then((value) => {
      if (live) setState({ org: organizationId, value });
    });
    return () => {
      live = false;
    };
  }, [organizationId, allowed]);
  if (!allowed) return false;
  return state && state.org === organizationId ? state.value : null;
}

export interface UsageText {
  runs: string;
  projects: string;
  resets: string | null;
}

const count = (n: unknown): n is number =>
  typeof n === "number" && Number.isInteger(n) && n >= 0;

/** Describes the server's usage figures, or returns null when they are missing or invalid, so the page can say
 * the usage is unavailable. A missing limit (null) means "no limit" only on the internal plan, which the server
 * assigns to the operator's own workspaces; anywhere else it is treated as invalid, never as unlimited. */
export function describeUsage(
  plan: unknown,
  usage: Partial<Record<keyof AppUsage, unknown>> | null | undefined,
): UsageText | null {
  if (!usage || typeof plan !== "string") return null;
  const internal = plan.toLowerCase() === "internal";
  const part = (used: unknown, limit: unknown, what: string) => {
    if (!count(used)) return null;
    if (limit === null) return internal ? `${used} used, no limit` : null;
    if (!count(limit)) return null;
    const left = Math.max(limit - used, 0);
    return `${used} of ${limit} used, ${left} left${left === 0 ? ` (${what} limit reached)` : ""}`;
  };
  const runs = part(usage.runs_used, usage.runs_limit, "run");
  const projects = part(usage.projects_used, usage.projects_limit, "project");
  if (runs === null || projects === null) return null;
  const end =
    typeof usage.period_end === "string" ? new Date(usage.period_end) : null;
  const resets =
    end && !Number.isNaN(end.getTime()) ? end.toISOString().slice(0, 10) : null;
  return { runs, projects, resets };
}

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"] as const;

/** One line for the runs list: where the run came from, the branch or commit label a pipeline sent, and how many
 * findings of each level it has. Counts are shown as numbers only; nothing is scored or graded. */
export function describeRun(run: {
  origin: "ci" | "upload";
  ref: string | null;
  counts: Record<string, number>;
}): { origin: string; ref: string | null; findings: string | null } {
  const parts = SEVERITY_ORDER.flatMap((level) => {
    const n = run.counts[level] ?? 0;
    return Number.isInteger(n) && n > 0 ? [`${n} ${level}`] : [];
  });
  const ref = run.ref ? run.ref.trim().slice(0, 120) : "";
  return {
    origin: run.origin === "ci" ? "CI pipeline" : "Browser upload",
    ref: ref || null,
    findings: parts.length ? parts.join(", ") : null,
  };
}
