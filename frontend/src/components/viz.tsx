import { niceMax } from "./charts";

export type DonutTone = "good" | "bad" | "warn" | "info";

export type DonutPart = { label: string; value: number; tone: DonutTone };

const R = 46;
const C = 2 * Math.PI * R;

/** A ring split into measured parts, with the total in the middle and a legend that repeats every number. */
export function Donut({
  parts,
  total,
  unit,
  label,
}: {
  parts: DonutPart[];
  total: number;
  unit: string;
  label: string;
}) {
  const sum = parts.reduce((s, p) => s + p.value, 0);
  const gap = parts.filter((p) => p.value > 0).length > 1 ? 3 : 0;
  let offset = 0;
  return (
    <div className="donut" role="img" aria-label={label}>
      <div className="donut-ring">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle className="donut-track" cx="60" cy="60" r={R} />
          {sum > 0 &&
            parts
              .filter((p) => p.value > 0)
              .map((p) => {
                const len = (p.value / sum) * C;
                const el = (
                  <circle
                    key={p.label}
                    className={`donut-part donut-${p.tone}`}
                    cx="60"
                    cy="60"
                    r={R}
                    strokeDasharray={`${Math.max(0, len - gap)} ${C}`}
                    strokeDashoffset={-offset}
                  />
                );
                offset += len;
                return el;
              })}
        </svg>
        <div className="donut-centre" aria-hidden="true">
          <strong>{total}</strong>
          <span>{unit}</span>
        </div>
      </div>
      <ul className="donut-legend">
        {parts.map((p) => (
          <li key={p.label}>
            <i className={`donut-key donut-${p.tone}`} aria-hidden="true" />
            <span>{p.label}</span>
            <b>{p.value}</b>
            <span className="donut-share">
              {sum > 0 ? `${Math.round((p.value / sum) * 100)}%` : "–"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export type Level = { label: string; value: number };

/** Percentile bars on one scale: the longer the bar, the slower the request. */
export function Levels({
  levels,
  unit,
  label,
}: {
  levels: Level[];
  unit: string;
  label: string;
}) {
  const { max } = niceMax(Math.max(0, ...levels.map((l) => l.value)));
  return (
    <ul className="levels" aria-label={label}>
      {levels.map((l) => (
        <li key={l.label}>
          <span className="levels-name">{l.label}</span>
          <span className="levels-track" aria-hidden="true">
            <i style={{ width: `${Math.max(1.5, (l.value / max) * 100)}%` }} />
          </span>
          <b className="levels-value">
            {l.value} {unit}
          </b>
        </li>
      ))}
    </ul>
  );
}
