import { reportUrl } from "../api";
import { formatDate } from "../format";
import type { ScanDetail } from "../types";
import { ErrorNotice, ScoreCard, SeverityBreakdown, StatusPill } from "./ui";

export function ReportButtons({ scanId }: { scanId: string }) {
  return (
    <div className="row" role="group" aria-label="Export report">
      <span className="muted small">Export:</span>
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

export default function ScanView({ scan }: { scan: ScanDetail }) {
  return (
    <div className="stack">
      {scan.status === "failed" && <ErrorNotice message={scan.error ?? "The scan failed."} />}
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
