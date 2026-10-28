import { useEffect, useState } from "react";
import { ApiError, listScans } from "../../api";
import type { ScanSummary } from "../../types";

export interface RecentScans {
  loading: boolean;
  error: string | null;
  items: ScanSummary[];
  /** Loads the list again, for the "Try again" button after an error. */
  retry: () => void;
}

type State = Omit<RecentScans, "retry">;

/** The latest scans, loaded on their own so one failing request cannot blank the rest of the dashboard. */
export function useRecentScans(refreshKey: string, limit = 6): RecentScans {
  const [state, setState] = useState<State>({
    loading: true,
    error: null,
    items: [],
  });
  const [attempt, setAttempt] = useState(0);
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
  }, [refreshKey, limit, attempt]);
  const retry = () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    setAttempt((n) => n + 1);
  };
  return { ...state, retry };
}
