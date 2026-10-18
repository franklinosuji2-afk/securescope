import { useState } from "react";
import { ApiError, retryScan } from "../api";
import type { ScanStatus } from "../types";

/** "Retry scan" after a failure or cancellation, "Scan again" otherwise. */
export function rescanLabel(status: ScanStatus): string {
  return status === "failed" || status === "cancelled"
    ? "Retry scan"
    : "Scan again";
}

/** Starts a new scan of the same address as an earlier one. The server re-checks ownership and limits. */
export default function RescanButton({
  scanId,
  host,
  status,
  onStarted,
}: {
  scanId: string;
  host: string;
  status: ScanStatus;
  onStarted: (scanId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = rescanLabel(status);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      onStarted((await retryScan(scanId)).id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "That did not work. Try again.",
      );
      setBusy(false);
    }
  }

  return (
    <>
      <button
        className="btn-ghost"
        type="button"
        disabled={busy}
        onClick={() => void start()}
        aria-label={`${label} of ${host}`}
      >
        {busy ? "Starting…" : label}
      </button>
      {error && (
        <p className="small sev-high" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
