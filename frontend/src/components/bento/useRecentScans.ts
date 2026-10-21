import { useEffect, useState } from "react";
import { ApiError, listScans } from "../../api";
import type { ScanSummary } from "../../types";

export interface RecentScans {
  loading: boolean;
  error: string | null;
  items: ScanSummary[];
}

/** The latest scans, loaded on their own so one failing request cannot blank the rest of the dashboard. */
export function useRecentScans(refreshKey: string, limit = 6): RecentScans {
  const [state, setState] = useState<RecentScans>({
    loading: true,
    error: null,
    items: [],
  });
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await listScans(limit, 0);
        if (!cancelled)
          setState({ loading: false, error: null, items: list?.items ?? [] });
      } catch (err) {
        if (cancelled) return;
        setState({
          loading: false,
          error:
            err instanceof ApiError ? err.message : "Could not load scans.",
          items: [],
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey, limit]);
  return state;
}
