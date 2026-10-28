import { useState, type ReactNode } from "react";
import { reportUrl } from "../../api";
import PdfReportButton from "../PdfReportButton";
import { formatDate } from "../../format";
import { chartPoints, deltaText, historySummary } from "../../overview";
import { buildHash } from "../../router";
import type { Overview, ReportFormat, Target } from "../../types";
import { FixFirstPanel } from "../Posture";
import { ErrorNotice, Loading, SeverityBadge, StatusPill } from "../ui";
import {
  priorityActions,
  scanOutcome,
  scannedHostSet,
  scanRecord,
  scoreScope,
  topIssues,
  weakestSite,
  type ScanRecord,
} from "./bentoLogic";
import SecurityScoreGauge from "./SecurityScoreGauge";
import { useRecentScans } from "./useRecentScans";

const TARGET_LABEL: Record<Target["status"], string> = {
  verified: "Ownership verified",
  pending: "Ownership not verified yet",
  expired: "Verification expired",
  reverify: "Needs re-verification",
};

/** Listed hosts show their score instead; the other labels say only what is known. */
const SCAN_RECORD_LABEL: Record<ScanRecord, string> = {
  listed: "in this overview",
  unlisted: "scanned, not among the sites listed here",
  never: "no completed scan on record",
  unknown: "not in this overview",
};

const FORMATS: { format: ReportFormat; label: string }[] = [
  { format: "html", label: "HTML" },
  { format: "md", label: "Markdown" },
  { format: "json", label: "JSON" },
];

function Card({
  id,
  title,
  className,
  children,
}: {
  id: string;
  title: string;
  className: string;
  children: ReactNode;
}) {
  return (
    <section className={`bento-card ${className}`} aria-labelledby={id}>
      <h2 id={id} className="bento-title">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** A picture of the score history; the same numbers are written out beside it, so it is decorative. */
function Sparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;
  const pts = chartPoints(scores, 168, 36);
  return (
    <svg
      viewBox="0 0 168 36"
      className="bento-spark"
      aria-hidden="true"
      focusable="false"
    >
      <polyline
        points={pts.map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
      />
    </svg>
  );
}

/**
 * The Overview as a grid of cards. Every value comes from the overview, targets and scan-list responses,
 * and a card that has no data says so instead of showing a stand-in.
 */
export default function BentoGrid({
  overview,
  targets,
  refreshKey,
  canManage,
  canRun,
  organizationId,
}: {
  overview: Overview;
  targets: Target[];
  refreshKey: string;
  canManage: boolean;
  canRun: boolean;
  /** The active organization, named in report links (plain links cannot send it as a header). */
  organizationId: string | null;
}) {
  const recent = useRecentScans(refreshKey);
  const [exportHost, setExportHost] = useState<string | null>(null);

  const site = weakestSite(overview.sites);
  const issues = topIssues(overview.sites);
  const scannedHosts = scannedHostSet(overview);
  const actions = priorityActions({
    targets,
    sites: overview.sites,
    scannedHosts,
    scans: recent.error || recent.loading ? null : recent.items,
    canManage,
    canRun,
  });
  const siteByHost = new Map(overview.sites.map((s) => [s.host, s]));
  const exportSite =
    overview.sites.find((s) => s.host === exportHost) ??
    site ??
    overview.sites[0] ??
    null;
  const siteTarget = site
    ? targets.find((t) => t.hostname === site.host)
    : undefined;

  return (
    <div className="bento-wrap">
      <div className="bento">
        <div className="bento-main">
          <div className="bento-cell bento-fix">
            <FixFirstPanel overview={overview} />
          </div>

          <Card
            id="bento-issues"
            title="Top open issues"
            className="bento-issues"
          >
            {issues.length === 0 ? (
              <p className="muted">
                No open findings in your latest scans. That means these passive
                checks found nothing, not that your sites are secure.
              </p>
            ) : (
              <>
                <p className="muted small">
                  The top open finding for each site.
                </p>
                <ul className="bento-list">
                  {issues.map((f) => (
                    <li key={`${f.host}-${f.finding_id}`}>
                      <a
                        className="bento-row"
                        href={buildHash("findings", f.scan_id, f.finding_id)}
                      >
                        <SeverityBadge severity={f.severity} />
                        <span className="bento-row-main">
                          <span className="bento-row-title">{f.title}</span>
                          <span className="muted small">
                            <code>{f.host}</code> · Open
                          </span>
                        </span>
                        <span className="chev" aria-hidden="true">
                          ▸
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Card>

          <Card
            id="bento-actions"
            title="Priority actions"
            className="bento-actions"
          >
            {recent.loading && <Loading label="Checking recent scans…" />}
            {recent.error && (
              <p className="muted small" role="note">
                Recent scans could not be loaded, so failed scans are not
                checked here.
              </p>
            )}
            {actions.length === 0 ? (
              !recent.loading && (
                <p className="muted">
                  Nothing needs action right now. This does not mean your sites
                  are secure.
                </p>
              )
            ) : (
              <ul className="bento-list">
                {actions.map((a) => (
                  <li key={a.id}>
                    <a className="bento-row" href={a.href}>
                      <span className="bento-row-main">
                        <span className="bento-row-title">{a.label}</span>
                        <span className="muted small">{a.detail}</span>
                      </span>
                      <span className="chev" aria-hidden="true">
                        ▸
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <p className="muted small">
              Rules, not advice: each item comes from your sites, scans and
              findings.
            </p>
          </Card>
          <Card
            id="bento-activity"
            title="Scan activity"
            className="bento-activity"
          >
            {recent.loading && <Loading label="Loading scans…" />}
            {recent.error && <ErrorNotice message={recent.error} />}
            {!recent.loading && !recent.error && recent.items.length === 0 && (
              <p className="muted">No scans yet.</p>
            )}
            {recent.items.length > 0 && (
              <ul className="bento-list">
                {recent.items.map((s) => (
                  <li key={s.id}>
                    <a className="bento-row" href={buildHash("history", s.id)}>
                      <span className="bento-row-main">
                        <span className="bento-row-title">
                          <code>{s.host}</code>
                        </span>
                        <span className="muted small">
                          {formatDate(s.created_at)} · {scanOutcome(s)}
                        </span>
                      </span>
                      <StatusPill status={s.status} />
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <a className="btn-ghost" href="#/history">
              All scans
            </a>
          </Card>

          <Card
            id="bento-targets"
            title="Site inventory"
            className="bento-targets"
          >
            {targets.length === 0 ? (
              <p className="muted">No sites added yet.</p>
            ) : (
              <ul className="bento-list">
                {targets.slice(0, 6).map((t) => {
                  const s = siteByHost.get(t.hostname);
                  return (
                    <li key={t.id} className="bento-inv">
                      <code>{t.hostname}</code>
                      <span className="muted small">
                        {TARGET_LABEL[t.status]} ·{" "}
                        {s
                          ? `score ${s.score ?? "–"}, ${s.open_total} open`
                          : SCAN_RECORD_LABEL[
                              scanRecord(
                                t.hostname,
                                overview.sites,
                                scannedHosts,
                              )
                            ]}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
            {targets.length > 6 && (
              <p className="muted small">
                Showing 6 of {targets.length} sites.
              </p>
            )}
            <a className="btn-ghost" href="#/targets">
              {canManage ? "Manage sites" : "View sites"}
            </a>
          </Card>
        </div>
        <div className="bento-side">
          <Card
            id="bento-score"
            title="Security posture"
            className="bento-score"
          >
            {site && site.score !== null ? (
              <>
                {siteTarget && (
                  <span
                    className={`bento-chip bento-chip-${siteTarget.status}`}
                    data-testid="bento-chip"
                  >
                    {TARGET_LABEL[siteTarget.status]}
                  </span>
                )}
                <div className="bento-score-body">
                  <SecurityScoreGauge
                    score={site.score}
                    grade={site.grade}
                    host={site.host}
                  />
                  <div className="bento-score-text">
                    <p className="bento-host">
                      <span className="muted small">
                        {scoreScope(overview)}
                      </span>
                      <code>{site.host}</code>
                    </p>
                    <p className="bento-big">
                      Score {site.score}
                      {site.grade ? `, grade ${site.grade}` : ""}
                    </p>
                    <p className="small">{deltaText(site.score_change)}</p>
                    <Sparkline scores={site.history.map((p) => p.score)} />
                    <p className="muted small">
                      {historySummary(site.history.map((p) => p.score))}
                    </p>
                  </div>
                </div>
                <p className="muted small">
                  A heuristic from passive checks of one page load. A high score
                  does not mean a site is secure. Last scanned{" "}
                  {formatDate(site.scanned_at)}.
                </p>
                <a
                  className="btn-ghost"
                  href={buildHash("findings", site.latest_scan_id)}
                >
                  Inspect this scan
                </a>
              </>
            ) : (
              <p className="muted">
                No scored scan yet. Run a scan of a verified site and its score
                will appear here.
              </p>
            )}
          </Card>

          <Card id="bento-exports" title="Reports" className="bento-exports">
            {exportSite ? (
              <>
                {overview.sites.length > 1 && (
                  <label className="bento-select small">
                    Site
                    <select
                      value={exportSite.host}
                      onChange={(e) => setExportHost(e.target.value)}
                    >
                      {overview.sites.map((s) => (
                        <option key={s.host} value={s.host}>
                          {s.host}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <p className="muted small">
                  Latest scan of <code>{exportSite.host}</code>. Each download
                  is recorded in the audit log.
                </p>
                <div className="row">
                  <PdfReportButton
                    scanId={exportSite.latest_scan_id}
                    host={exportSite.host}
                  />
                  {FORMATS.map(({ format, label }) => (
                    <a
                      key={format}
                      className="btn-ghost"
                      href={reportUrl(
                        exportSite.latest_scan_id,
                        format,
                        organizationId,
                      )}
                      download
                      aria-label={`Download ${label} report for ${exportSite.host}`}
                    >
                      {label}
                    </a>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">
                Reports appear after your first completed scan.
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
