import { coverage } from "../overview";
import type { Overview, Target } from "../types";

/**
 * Four numbers computed only from the data the overview already has. Nothing is estimated. The overview
 * lists only the most recently scanned sites, so when it is known to leave some out, the notes say so.
 */
export default function SummaryCards({
  overview,
  targets,
}: {
  overview: Overview;
  targets: Target[];
}) {
  const { listed, total, partial } = coverage(overview);
  const subset = `on the ${listed} most recently scanned sites`;
  const verified = targets.filter((t) => t.status === "verified").length;
  const open = overview.sites.reduce((sum, s) => sum + s.open_total, 0);
  const urgent = overview.sites.reduce(
    (sum, s) => sum + (s.open_counts.critical ?? 0) + (s.open_counts.high ?? 0),
    0,
  );
  const scores = overview.sites
    .map((s) => s.score)
    .filter((n): n is number => n !== null);
  const lowest = scores.length ? Math.min(...scores) : null;
  const items: { label: string; value: string; note: string }[] = [
    {
      label: "Verified sites",
      value: String(verified),
      note: `${total ?? listed} scanned`,
    },
    {
      label: "Open findings",
      value: String(open),
      note: partial ? subset : "across your latest scans",
    },
    {
      label: "Critical and high",
      value: String(urgent),
      note:
        urgent > 0
          ? "fix these first"
          : partial
            ? `none ${subset}`
            : "none open",
    },
    {
      label: "Lowest heuristic score",
      value: lowest === null ? "–" : String(lowest),
      note: partial
        ? `of the ${listed} most recently scanned sites; a heuristic`
        : "a heuristic, not proof of security",
    },
  ];
  return (
    <ul className="summary-grid" aria-label="Summary">
      {items.map((i) => (
        <li key={i.label} className="card summary-card">
          <div className="stat-label">{i.label}</div>
          <div className="stat-value">{i.value}</div>
          <div className="muted small">{i.note}</div>
        </li>
      ))}
    </ul>
  );
}
