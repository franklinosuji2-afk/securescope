import { useState } from "react";
import { ApiError, recheckFinding } from "../api";
import { useAuth } from "../auth";
import type { Finding, FindingRecheck, ScanDetail } from "../types";
import { canScan } from "../types";
import { ErrorNotice } from "./ui";

const HEADLINE: Record<FindingRecheck["outcome"], string> = {
  not_seen: "Not seen this time.",
  still_present: "Still there.",
  could_not_check: "Could not check.",
};

/** "Is it fixed?": looks at the site once more and reports on this one finding. Nothing is saved. */
export default function RecheckPanel({
  scan,
  finding,
}: {
  scan: ScanDetail;
  finding: Finding;
}) {
  const { organization } = useAuth();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FindingRecheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!organization || !canScan(organization.role)) return null;
  if (scan.status !== "completed") return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await recheckFinding(scan.id, finding.id));
    } catch (err) {
      setResult(null);
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Something went wrong.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card detail-section" aria-labelledby="d-recheck">
      <h2 id="d-recheck">Check if it is fixed</h2>
      <p className="muted small">
        Looks at {scan.host} once more and reports on this finding only. It does
        not start a scan, uses none of your monthly scans, and does not change
        the score or the finding&apos;s status.
      </p>
      <div className="row">
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => void run()}
        >
          {busy ? "Checking…" : "Check this finding again"}
        </button>
      </div>
      {error && <ErrorNotice message={error} />}
      {result && (
        <div
          className={`notice ${result.outcome === "not_seen" ? "notice-info" : ""}`}
          role="status"
          data-testid="recheck-result"
        >
          <strong>{HEADLINE[result.outcome]}</strong> {result.message}
        </div>
      )}
    </section>
  );
}
