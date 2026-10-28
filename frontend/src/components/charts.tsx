import type { ReactNode } from "react";

export type Tone = "cyan" | "violet" | "pink" | "lime" | "green" | "amber";

/** A round axis maximum (four equal steps) so the gridlines read as whole numbers. */
export function niceMax(max: number): { max: number; ticks: number[] } {
  const raw = Math.max(1, max) / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step =
    [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
  const top = Math.max(4, step * 4);
  const s = top / 4;
  return { max: top, ticks: [4, 3, 2, 1, 0].map((n) => n * s) };
}

export type Trend = "up" | "down" | "flat";

/** Up, down or flat, from two measured numbers. */
export function trendOf(current: number, previous: number): Trend {
  if (previous === 0 || current === previous) return "flat";
  return current > previous ? "up" : "down";
}

/** A tiny trend line from measured values. Decorative: the figure and its note carry the meaning. */
function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo;
  const last = values.length - 1;
  const points = values
    .map((v, i) => {
      const x = (i / last) * 100;
      const y = span === 0 ? 14 : 26 - ((v - lo) / span) * 24;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      className="kpi-spark"
      viewBox="0 0 100 28"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline points={points} />
    </svg>
  );
}

const TREND_MARK: Record<Trend, string> = { up: "▲", down: "▼", flat: "" };

/** A figure under a small coloured label, like the tiles of a monitoring dashboard. */
export function Kpi({
  label,
  value,
  note,
  tone,
  trend,
  spark,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone: Tone;
  trend?: Trend;
  /** Measured values over the period, drawn as a small line. Leave out when there is no series. */
  spark?: number[];
}) {
  return (
    <li className={`card kpi kpi-${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {note ? (
        <div className={`kpi-note${trend ? ` kpi-${trend}` : ""}`}>
          {trend && TREND_MARK[trend] ? (
            <span className="kpi-mark" aria-hidden="true">
              {TREND_MARK[trend]}{" "}
            </span>
          ) : null}
          {note}
        </div>
      ) : null}
      {spark ? <Spark values={spark} /> : null}
    </li>
  );
}

/** A dashboard panel: a title (with an optional aside such as a legend) above its content. */
export function Panel({
  title,
  aside,
  className = "",
  children,
}: {
  title: string;
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`card panel ${className}`.trim()}>
      <div className="panel-head">
        <h2>{title}</h2>
        {aside ? <div className="panel-aside">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** One label and value per line, divided by thin rules. */
export function Rows({ children }: { children: ReactNode }) {
  return <ul className="rows">{children}</ul>;
}

export function Row({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <li className="row-item">
      <span>{label}</span>
      <strong>{children}</strong>
    </li>
  );
}

/** A setting that is on or off, shown with a dot as well as the word. */
export function Flag({
  on,
  yes,
  no,
}: {
  on: boolean;
  yes: string;
  no: string;
}) {
  return (
    <span className={`flag ${on ? "flag-on" : "flag-off"}`}>
      <i aria-hidden="true" />
      {on ? yes : no}
    </span>
  );
}
