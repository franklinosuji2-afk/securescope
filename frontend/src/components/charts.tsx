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

/** A figure under a small coloured label, like the tiles of a monitoring dashboard. */
export function Kpi({
  label,
  value,
  note,
  tone,
  trend,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone: Tone;
  trend?: Trend;
}) {
  return (
    <li className={`card kpi kpi-${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {note ? (
        <div className={`kpi-note${trend ? ` kpi-${trend}` : ""}`}>{note}</div>
      ) : null}
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

function Axis({ ticks, unit }: { ticks: number[]; unit?: string }) {
  return (
    <div className="chart-axis" aria-hidden="true">
      {ticks.map((t) => (
        <span key={t}>{t}</span>
      ))}
      {unit ? <span className="chart-unit">{unit}</span> : null}
    </div>
  );
}

function Grid() {
  return (
    <div className="chart-grid" aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
      <i />
    </div>
  );
}

export type Day = { date: string; visitors: number; views: number };

/** Daily histogram of visitors (columns) with page views as a line, both on one scale. */
export function DailyHistogram({
  series,
  label,
}: {
  series: Day[];
  label: string;
}) {
  const { max, ticks } = niceMax(Math.max(0, ...series.map((d) => d.views)));
  const n = Math.max(1, series.length);
  const points = series
    .map(
      (d, i) =>
        `${(((i + 0.5) / n) * 100).toFixed(2)},${(100 - (d.views / max) * 100).toFixed(2)}`,
    )
    .join(" ");
  const first = series[0]?.date.slice(5) ?? "";
  const mid = series[Math.floor(series.length / 2)]?.date.slice(5) ?? "";
  const last = series[series.length - 1]?.date.slice(5) ?? "";
  return (
    <div className="chart" role="img" aria-label={label}>
      <Axis ticks={ticks} />
      <div className="chart-plot">
        <Grid />
        <div className="chart-cols" aria-hidden="true">
          {series.map((d) => (
            <div
              key={d.date}
              className="chart-col"
              title={`${d.date}: ${d.visitors} visitors, ${d.views} views`}
            >
              <b
                className="chart-bar chart-bar-cyan"
                style={{ height: `${(d.visitors / max) * 100}%` }}
              />
            </div>
          ))}
        </div>
        <svg
          className="chart-line"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polyline points={points} />
        </svg>
      </div>
      <div className="chart-x" aria-hidden="true">
        <span>{first}</span>
        <span>{mid}</span>
        <span>{last}</span>
      </div>
    </div>
  );
}

export type Column = { label: string; value: number; tone: Tone };

/** A few labelled columns, for comparing measured values (latency percentiles, scan outcomes). */
export function ColumnChart({
  columns,
  unit,
  label,
}: {
  columns: Column[];
  unit?: string;
  label: string;
}) {
  const { max, ticks } = niceMax(Math.max(0, ...columns.map((c) => c.value)));
  return (
    <div className="chart chart-short" role="img" aria-label={label}>
      <Axis ticks={ticks} unit={unit} />
      <div className="chart-plot">
        <Grid />
        <div className="chart-cols chart-cols-wide" aria-hidden="true">
          {columns.map((c) => (
            <div
              key={c.label}
              className="chart-col"
              title={`${c.label}: ${c.value}`}
            >
              <span className="chart-val">{c.value}</span>
              <b
                className={`chart-bar chart-bar-${c.tone}`}
                style={{ height: `${(c.value / max) * 100}%` }}
              />
            </div>
          ))}
        </div>
      </div>
      <div className="chart-x chart-x-cols" aria-hidden="true">
        {columns.map((c) => (
          <span key={c.label}>{c.label}</span>
        ))}
      </div>
    </div>
  );
}
