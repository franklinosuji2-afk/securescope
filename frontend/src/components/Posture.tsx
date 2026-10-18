import { formatDate, severityLabel } from "../format";
import { deltaText, openCounts, totalOf, type FixFirst, type SiteSummary } from "../overview";
import { buildHash } from "../router";
import type { ScanDetail } from "../types";
import { SEVERITIES } from "../types";
import { gradeClass } from "../format";
import { SeverityBadge } from "./ui";
import { guidanceFor } from "../guidance";

export function FixFirstPanel({ fix }: { fix: FixFirst | null }) {
  if (!fix) {
    return (
      <section className="card fix-first" aria-labelledby="fix-title">
        <h2 id="fix-title">Fix this first</h2>
        <p>
          Nothing open. The latest scans report no open findings. That means these passive checks found nothing, not
          that the sites are secure.
        </p>
      </section>
    );
  }
  const { finding, scan, others } = fix;
  const guide = guidanceFor(finding.id);
  return (
    <section className="card fix-first" aria-labelledby="fix-title">
      <h2 id="fix-title">Fix this first</h2>
      <div className="fix-head">
        <SeverityBadge severity={finding.severity} />
        <strong>{finding.title}</strong>
        <span className="muted small">on {scan.host}</span>
      </div>
      <p>{guide.impact}</p>
      <p className="small">
        <strong>What to do:</strong> {finding.remediation}
      </p>
      <div className="row">
        <a className="btn btn-link" href={buildHash("findings", scan.id, finding.id)}>
          See the evidence and fix
        </a>
        {others > 0 && (
          <span className="muted small">
            {others} other open finding{others === 1 ? "" : "s"} across your sites
          </span>
        )}
      </div>
    </section>
  );
}

export function SiteCard({ site, detail }: { site: SiteSummary; detail: ScanDetail | undefined }) {
  const counts = detail ? openCounts(detail.findings) : null;
  const total = counts ? totalOf(counts) : null;
  const trendClass = site.delta === null || site.delta === 0 ? "" : site.delta > 0 ? "trend-up" : "trend-down";
  return (
    <li className="card site-card" aria-label={site.host}>
      <div className="site-head">
        <h3>{site.host}</h3>
        <span className="stat-value site-score">
          {site.latest.score ?? "–"}
          {site.latest.grade && <span className={gradeClass(site.latest.grade)}>Grade {site.latest.grade}</span>}
        </span>
      </div>
      <p className={`small ${trendClass || "muted"}`}>{deltaText(site.delta)}</p>
      {counts && total !== null ? (
        total === 0 ? (
          <p className="small">No open findings.</p>
        ) : (
          <p className="small">
            <strong>{total} open</strong>:{" "}
            {SEVERITIES.filter((s) => counts[s]).map((s, i, a) => (
              <span key={s}>
                <span className={`sev-${s}`}>
                  {counts[s]} {severityLabel(s)}
                </span>
                {i < a.length - 1 ? ", " : ""}
              </span>
            ))}
          </p>
        )
      ) : (
        <p className="muted small">Open findings unavailable.</p>
      )}
      <p className="muted small">Last scanned {formatDate(site.latest.finished_at ?? site.latest.created_at)}</p>
      <a className="btn-ghost" href={buildHash("findings", site.latest.id)}>
        View findings
      </a>
    </li>
  );
}

export function SiteCards({ sites, details }: { sites: SiteSummary[]; details: Record<string, ScanDetail> }) {
  return (
    <ul className="site-grid" aria-label="Your sites">
      {sites.map((site) => (
        <SiteCard key={site.host} site={site} detail={details[site.latest.id]} />
      ))}
    </ul>
  );
}

export default function Posture({
  sites,
  details,
  fix,
}: {
  sites: SiteSummary[];
  details: Record<string, ScanDetail>;
  fix: FixFirst | null;
}) {
  return (
    <div className="stack">
      <FixFirstPanel fix={fix} />
      <SiteCards sites={sites} details={details} />
    </div>
  );
}
