import { useEffect, useState } from "react";
import { ApiError, getScan, listScans, listTargets } from "./api";
import { siteSummaries } from "./overview";
import type { ScanDetail, ScanSummary, Target } from "./types";

export interface OverviewData {
  loading: boolean;
  error: string | null;
  targets: Target[];
  scans: ScanSummary[];
  /** Full detail of the latest completed scan per site, keyed by scan id. */
  details: Record<string, ScanDetail>;
}

const EMPTY: OverviewData = { loading: true, error: null, targets: [], scans: [], details: {} };

/** Loads what the Overview needs. `refreshKey` changes when a scan starts or finishes. */
export function useOverviewData(refreshKey: string): OverviewData {
  const [state, setState] = useState<OverviewData>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [targetsResult, scansResult] = await Promise.all([listTargets(), listScans(50)]);
        const targets = targetsResult ?? [];
        const scans = scansResult?.items ?? [];
        const latest = siteSummaries(targets, scans).map((s) => s.latest.id);
        const settled = await Promise.allSettled(latest.map((id) => getScan(id)));
        const details: Record<string, ScanDetail> = {};
        settled.forEach((r, i) => {
          if (r.status === "fulfilled" && r.value?.findings) details[latest[i]!] = r.value;
        });
        if (!cancelled) setState({ loading: false, error: null, targets, scans, details });
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Could not load the overview.";
        setState((prev) => ({ ...prev, loading: false, error: message }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return state;
}
