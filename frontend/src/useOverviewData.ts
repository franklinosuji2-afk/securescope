import { useEffect, useState } from "react";
import { ApiError, getOverview, listTargets } from "./api";
import type { Overview, Target } from "./types";

export interface OverviewData {
  loading: boolean;
  error: string | null;
  targets: Target[];
  overview: Overview;
}

const EMPTY_OVERVIEW: Overview = { sites: [], fix_first: null, other_open: 0 };
const EMPTY: OverviewData = {
  loading: true,
  error: null,
  targets: [],
  overview: EMPTY_OVERVIEW,
};

/** Loads what the Overview needs in two requests. `refreshKey` changes when a scan starts or finishes. */
export function useOverviewData(refreshKey: string): OverviewData {
  const [state, setState] = useState<OverviewData>(EMPTY);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [targets, overview] = await Promise.all([
          listTargets(),
          getOverview(),
        ]);
        if (!cancelled)
          setState({
            loading: false,
            error: null,
            targets: targets ?? [],
            overview: overview?.sites ? overview : EMPTY_OVERVIEW,
          });
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Could not load the overview.";
        setState((prev) => ({ ...prev, loading: false, error: message }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return state;
}
