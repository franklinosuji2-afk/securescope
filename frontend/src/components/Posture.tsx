import { gradeClass, formatDate, severityLabel } from "../format";
import { guidanceFor } from "../guidance";
import { deltaText } from "../overview";
import { buildHash } from "../router";
import RescanButton from "./RescanButton";
import type { Overview, SitePosture } from "../types";
import { SEVERITIES } from "../types";
import ScoreTrend from "./ScoreTrend";
import { SeverityBadge } from "./ui";

export function FixFirstPanel({ overview }: { overview: Overview }) {
  const fix = overview.fix_first;
  if (!fix) {
    return (
      <section className="card fix-first" aria-labelledby="fix-title">
        <h2 id="fix-title">Fix this first</h2>
        <p>
          Nothing open. The latest scans report no open findings. That means
          these passive checks found nothing, not that the sites are secure.
        </p>
      </section>
    );
  }
  const guide = guidanceFor(fix.finding_id);
  return (
    <section className="card fix-first" aria-labelledby="fix-title">
      <h2 id="fix-title">Fix this first</h2>
      <div className="fix-head">
        <SeverityBadge severity={fix.severity} />
        <strong>{fix.title}</strong>
        <span className="muted small">on {fix.host}</span>
      </div>
      <p>{guide.impact}</p>
      <p className="small">
        <strong>What to do:</strong> {fix.remediation}
      </p>
      <div className="row">
        <a
          className="btn btn-link"
          href={buildHash("findings", fix.scan_id, fix.finding_id)}
        >
          See the evidence and fix
        </a>
        {overview.other_open > 0 && (
          <span className="muted small">
            {overview.other_open} other open finding
            {overview.other_open === 1 ? "" : "s"} across your sites
          </span>
        )}
      </div>
    </section>
  );
}

export function SiteCard({
  site,
  onScanAgain,
}: {
  site: SitePosture;
  onScanAgain?: (scanId: string) => void;
}) {
  const trendClass =
    site.score_change === null || site.score_change === 0
      ? "muted"
      : site.score_change > 0
        ? "trend-up"
        : "trend-down";
  return (
    <li className="card site-card" aria-label={site.host}>
      <div className="site-head">
        <h3>{site.host}</h3>
        <span className="stat-value site-score">
          {site.score ?? "–"}
          {site.grade && (
            <span className={gradeClass(site.grade)}>Grade {site.grade}</span>
          )}
        </span>
      </div>
      <p className={`small ${trendClass}`}>{deltaText(site.score_change)}</p>
      <ScoreTrend history={site.history} />
      {site.open_total === 0 ? (
        <p className="small">No open findings.</p>
      ) : (
        <p className="small">
          <strong>{site.open_total} open</strong>:{" "}
          {SEVERITIES.filter((s) => site.open_counts[s]).map((s, i, a) => (
            <span key={s}>
              <span className={`sev-${s}`}>
                {site.open_counts[s]} {severityLabel(s)}
              </span>
              {i < a.length - 1 ? ", " : ""}
            </span>
          ))}
        </p>
      )}
      <p className="muted small">Last scanned {formatDate(site.scanned_at)}</p>
      <a
        className="btn-ghost"
        href={buildHash("findings", site.latest_scan_id)}
      >
        View findings
      </a>
      {onScanAgain && (
        <RescanButton
          scanId={site.latest_scan_id}
          host={site.host}
          status="completed"
          onStarted={onScanAgain}
        />
      )}
    </li>
  );
}

export default function Posture({
  overview,
  onScanAgain,
}: {
  overview: Overview;
  onScanAgain?: (scanId: string) => void;
}) {
  return (
    <div className="stack">
      <FixFirstPanel overview={overview} />
      <ul className="site-grid" aria-label="Your sites">
        {overview.sites.map((site) => (
          <SiteCard key={site.host} site={site} onScanAgain={onScanAgain} />
        ))}
      </ul>
    </div>
  );
}
