import { useCallback, useEffect, useState } from "react";
import { ApiError, getScan } from "./api";
import type { ScanDetail } from "./types";

const POLL_MS = 1200;

export interface ScanState {
  scan: ScanDetail | null;
  loading: boolean;
  error: string | null;
  /** Fetches the scan again, for example after a finding's status was changed. */
  reload: () => void;
}

interface Result {
  id: string;
  scan: ScanDetail | null;
  error: string | null;
}

/** Loads one scan and polls until it reaches a final state. */
export function useScan(scanId: string | null): ScanState {
  const [result, setResult] = useState<Result | null>(null);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    if (!scanId) return;
    let cancelled = false;
    let timer: number | undefined;

    const load = async () => {
      try {
        const scan = await getScan(scanId);
        if (cancelled) return;
        setResult({ id: scanId, scan, error: null });
        if (scan.status === "queued" || scan.status === "running") {
          timer = window.setTimeout(load, POLL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong loading this scan.";
        setResult({ id: scanId, scan: null, error: message });
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [scanId, version]);

  if (!scanId) return { scan: null, loading: false, error: null, reload };
  if (!result || result.id !== scanId)
    return { scan: null, loading: true, error: null, reload };
  return { scan: result.scan, loading: false, error: result.error, reload };
}
