import { formatDate } from "../../format";
import { buildHash } from "../../router";
import type { SitePosture, Target } from "../../types";
import { ErrorNotice, Loading, StatusPill } from "../ui";
import { inventoryCounts, scanOutcome, TARGET_LABEL } from "./bentoLogic";
import type { RecentScans } from "./useRecentScans";

/** Ownership state as a mark that does not rely on colour: a tick, a clock or an exclamation point. */
const OWNERSHIP_MARK: Record<Target["status"], string> = {
  verified: "✓",
  pending: "…",
  expired: "!",
  reverify: "!",
};

/** The latest scans as a feed: one link per scan, with its result and a status word. */
export function ScanActivityList({ recent }: { recent: RecentScans }) {
  if (recent.loading)
    return (
      <>
        <Loading label="Loading scans…" />
        <ul className="act act-skeleton" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <li key={i}>
              <span />
              <span />
            </li>
          ))}
        </ul>
      </>
    );
  if (recent.error)
    return (
      <div className="act-problem">
        <ErrorNotice message={recent.error} />
        <button type="button" className="btn-ghost" onClick={recent.retry}>
          Try again
        </button>
      </div>
    );
  if (recent.items.length === 0)
    return (
      <div className="act-empty">
        <p>No scans yet.</p>
        <p className="muted small">
          Each scan you run is listed here with its result, newest first.
        </p>
      </div>
    );
  return (
    <ul className="act">
      {recent.items.map((s) => (
        <li key={s.id} className={`act-item act-${s.status}`}>
          <a className="act-row" href={buildHash("history", s.id)}>
            <span className="act-main">
              <span className="act-host">
                <code>{s.host}</code>
              </span>
              <span className="act-outcome">{scanOutcome(s)}</span>
              <span className="act-date muted small">
                {formatDate(s.created_at)}
              </span>
            </span>
            <StatusPill status={s.status} />
            <span className="chev" aria-hidden="true">
              ▸
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** The sites in this workspace: ownership first, then what the latest scan found. */
export function SiteInventoryList({
  targets,
  siteByHost,
  describe,
  canManage,
}: {
  targets: Target[];
  siteByHost: Map<string, SitePosture>;
  /** What is known about a site that has no entry in the overview. */
  describe: (target: Target) => string;
  canManage: boolean;
}) {
  if (targets.length === 0)
    return (
      <div className="act-empty">
        <p>No sites added yet.</p>
        <p className="muted small">
          {canManage
            ? "Add a site you own, verify it, and run its first scan."
            : "Sites appear here once someone with access adds them."}
        </p>
      </div>
    );
  const counts = inventoryCounts(targets);
  return (
    <>
      <p className="inv-summary muted small">
        {counts.total} {counts.total === 1 ? "site" : "sites"}
        {counts.verified > 0 && <>, {counts.verified} verified</>}
        {counts.needAttention > 0 && <>, {counts.needAttention} to verify</>}
      </p>
      <ul className="inv">
        {targets.slice(0, 6).map((t) => {
          const s = siteByHost.get(t.hostname);
          return (
            <li key={t.id} className={`inv-item inv-${t.status}`}>
              <span className="inv-mark" aria-hidden="true">
                {OWNERSHIP_MARK[t.status]}
              </span>
              <span className="inv-main">
                <code className="inv-host">{t.hostname}</code>
                <span className="muted small">
                  {TARGET_LABEL[t.status]} ·{" "}
                  {s
                    ? `score ${s.score ?? "–"}, ${s.open_total} open`
                    : describe(t)}
                </span>
              </span>
              {s && s.score !== null && (
                <span className="inv-score" aria-hidden="true">
                  <b>{s.score}</b>
                  {s.grade && <i>{s.grade}</i>}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {targets.length > 6 && (
        <p className="muted small">Showing 6 of {targets.length} sites.</p>
      )}
    </>
  );
}
