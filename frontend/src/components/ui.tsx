import type { ReactNode } from "react";
import { gradeClass, severityLabel } from "../format";
import type { ScanStatus, Severity } from "../types";
import { SEVERITIES } from "../types";

/** Shape + text label, so severity never depends on colour alone. */
const SEVERITY_GLYPH: Record<Severity, string> = { critical: "◆", high: "▲", medium: "■", low: "●", info: "○" };

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`sev sev-${severity}`}>
      <span className="sev-glyph" aria-hidden="true">
        {SEVERITY_GLYPH[severity]}
      </span>
      {severityLabel(severity)}
    </span>
  );
}

export function StatusPill({ status }: { status: ScanStatus }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={`pill pill-${status}`}>
      {(status === "running" || status === "queued") && <span className="spinner" aria-hidden="true" />}
      {label}
    </span>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="notice notice-error" role="alert">
      {message}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card empty">
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="row muted" role="status">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function ScoreCard({ score, grade, note }: { score: number | null; grade: string | null; note: string }) {
  return (
    <div className="card">
      <div className="stat-label">Heuristic score</div>
      <div className="stat-value">
        {score ?? "–"}
        {grade && <span className={gradeClass(grade)}>Grade {grade}</span>}
      </div>
      <p className="muted small">{note}</p>
    </div>
  );
}

export function SeverityBreakdown({ counts }: { counts: Partial<Record<Severity, number>> }) {
  const max = Math.max(1, ...SEVERITIES.map((s) => counts[s] ?? 0));
  return (
    <div className="card">
      <div className="card-title">
        <h2>Severity breakdown</h2>
      </div>
      <ul className="bars">
        {SEVERITIES.map((s) => {
          const n = counts[s] ?? 0;
          return (
            <li key={s} className={`bar-row sev-${s}`}>
              <span>{severityLabel(s)}</span>
              <div className="bar-track" aria-hidden="true">
                <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
              </div>
              <span className="bar-count" style={{ color: "var(--text)" }}>
                {n}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
