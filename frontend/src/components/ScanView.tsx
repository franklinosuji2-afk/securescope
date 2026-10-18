import { useState } from "react";
import { ApiError, cancelScan, reportUrl, retryScan } from "../api";
import { formatDate } from "../format";
import type { ScanDetail } from "../types";
import { isActive } from "../types";
import { ErrorNotice, ScoreCard, SeverityBreakdown, StatusPill } from "./ui";

export function ReportButtons({ scanId }: { scanId: string }) {
  return (
    <div className="row" role="group" aria-label="Export report">
      <span className="muted small">Export:</span>
      <a className="btn-ghost" href={reportUrl(scanId, "pdf")} download>
        PDF
      </a>
      <a className="btn-ghost" href={reportUrl(scanId, "html")} download>
        HTML
      </a>
      <a className="btn-ghost" href={reportUrl(scanId, "md")} download>
        Markdown
      </a>
      <a className="btn-ghost" href={reportUrl(scanId, "json")} download>
        JSON
      </a>
    </div>
  );
}

export function ScanStatusCard({ scan }: { scan: ScanDetail }) {
  return (
    <div className="card">
      <div className="stat-label">Status</div>
      <div className="stat-value" style={{ fontSize: "1.2rem" }}>
        <StatusPill status={scan.status} />
      </div>
      <p className="muted small" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {scan.target_url}
      </p>
      <p className="muted small">Started {formatDate(scan.created_at)}</p>
    </div>
  );
}

export function TargetMeta({ scan }: { scan: ScanDetail }) {
  const m = scan.metadata;
  return (
    <div className="card">
      <div className="card-title">
        <h2>Target metadata</h2>
      </div>
      {!m ? (
        <p className="muted">Metadata appears once the first response has been received.</p>
      ) : (
        <dl className="meta">
          <dt>Host</dt>
          <dd>{m.host}</dd>
          <dt>Resolved</dt>
          <dd>{m.resolved_addresses.join(", ") || "–"}</dd>
          <dt>Final URL</dt>
          <dd>{m.final_url ?? "–"}</dd>
          <dt>Status</dt>
          <dd>{m.status_code ?? "–"}</dd>
          <dt>Content type</dt>
          <dd>{m.content_type ?? "–"}</dd>
          <dt>Response time</dt>
          <dd>{m.response_time_ms != null ? `${m.response_time_ms} ms` : "–"}</dd>
          <dt>Requests made</dt>
          <dd>{m.requests_made}</dd>
          <dt>Redirects</dt>
          <dd>{m.redirect_chain.length}</dd>
        </dl>
      )}
    </div>
  );
}

/** Stop a scan that is still going, or run a failed or cancelled one again. */
export function ScanActions({
  scan,
  onChanged,
  onRetried,
}: {
  scan: ScanDetail;
  /** Called after a cancel, so the scan can be loaded again. */
  onChanged: () => void;
  /** Called with the id of the new scan after a retry. */
  onRetried: (scanId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That did not work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const cancel = () =>
    run(async () => {
      await cancelScan(scan.id);
      setMessage("Scan cancelled. No findings were recorded.");
      onChanged();
    });
  const retry = () =>
    run(async () => {
      const next = await retryScan(scan.id);
      onRetried(next.id);
    });

  return (
    <div className="stack-sm">
      <div className="row">
        {isActive(scan.status) && (
          <button className="btn-ghost" type="button" disabled={busy} onClick={() => void cancel()}>
            {busy ? "Cancelling…" : "Cancel scan"}
          </button>
        )}
        {(scan.status === "failed" || scan.status === "cancelled") && (
          <button className="btn-ghost" type="button" disabled={busy} onClick={() => void retry()}>
            {busy ? "Starting…" : "Retry scan"}
          </button>
        )}
      </div>
      <p className="visually-hidden" role="status">
        {message}
      </p>
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

export default function ScanView({
  scan,
  onChanged,
  onRetried,
}: {
  scan: ScanDetail;
  onChanged?: () => void;
  onRetried?: (scanId: string) => void;
}) {
  return (
    <div className="stack">
      {scan.status === "failed" && <ErrorNotice message={scan.error ?? "The scan failed."} />}
      {scan.status === "cancelled" && (
        <div className="notice notice-info" role="note">
          This scan was cancelled before it finished. No findings or score were recorded, and earlier results are
          unchanged.
        </div>
      )}
      {onChanged && onRetried && <ScanActions scan={scan} onChanged={onChanged} onRetried={onRetried} />}
      <div className="grid grid-3">
        <ScanStatusCard scan={scan} />
        <ScoreCard score={scan.score} grade={scan.grade} note={scan.score_note} />
        <SeverityBreakdown counts={scan.counts} />
      </div>
      <TargetMeta scan={scan} />
      {scan.status === "completed" && <ReportButtons scanId={scan.id} />}
    </div>
  );
}
