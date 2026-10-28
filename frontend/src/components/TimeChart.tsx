import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { niceMax } from "./charts";

export type TimePoint = { date: string; visitors: number; views: number };

type SeriesKey = "visitors" | "views" | "previous";

const HEIGHT = 264;
const PAD = { left: 40, right: 14, top: 14, bottom: 28 };

/** A smooth curve through the points that never overshoots a value (monotone cubic, as in d3). */
export function smoothPath(points: [number, number][]): string {
  const n = points.length;
  if (n === 0) return "";
  const first = points[0]!;
  if (n === 1) return `M${first[0]},${first[1]}`;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    dx.push(b[0] - a[0]);
    slope.push(dx[i]! === 0 ? 0 : (b[1] - a[1]) / dx[i]!);
  }
  const t: number[] = new Array<number>(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    const s0 = slope[i - 1]!;
    const s1 = slope[i]!;
    const h0 = dx[i - 1]!;
    const h1 = dx[i]!;
    const p = (s0 * h1 + s1 * h0) / (h0 + h1 || 1);
    t[i] =
      (Math.sign(s0) + Math.sign(s1)) *
        Math.min(Math.abs(s0), Math.abs(s1), 0.5 * Math.abs(p)) || 0;
  }
  if (n === 2) {
    t[0] = slope[0]!;
    t[1] = slope[0]!;
  } else {
    t[0] = (3 * slope[0]! - t[1]!) / 2;
    t[n - 1] = (3 * slope[n - 2]! - t[n - 2]!) / 2;
  }
  let d = `M${first[0]},${first[1]}`;
  for (let i = 0; i < n - 1; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    const h = dx[i]! / 3;
    d += `C${a[0] + h},${a[1] + t[i]! * h},${b[0] - h},${b[1] - t[i + 1]! * h},${b[0]},${b[1]}`;
  }
  return d;
}

function dayLabel(date: string): string {
  const d = new Date(`${date}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
}

function shortDay(date: string): string {
  const d = new Date(`${date}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function versus(current: number, before: number | undefined) {
  if (before === undefined) return null;
  if (before === 0) return { text: `vs ${before}`, tone: "flat" };
  const pct = Math.round(((current - before) / before) * 100);
  if (pct === 0) return { text: `vs ${before}, no change`, tone: "flat" };
  return {
    text: `${pct > 0 ? "▲ +" : "▼ "}${pct}% vs ${before}`,
    tone: pct > 0 ? "up" : "down",
  };
}

/**
 * Visitors and page views per day as smooth areas, with the previous period as a dashed line.
 * Hover or use the arrow keys for exact numbers; the legend switches each line on or off.
 */
export default function TimeChart({
  series,
  previous,
  label,
}: {
  series: TimePoint[];
  previous: TimePoint[] | null;
  label: string;
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const [off, setOff] = useState<ReadonlySet<SeriesKey>>(new Set());
  const [spoken, setSpoken] = useState("");

  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(([entry]) => {
      const w = Math.floor(entry?.contentRect.width ?? 0);
      if (w > 0) setWidth(w);
    });
    watch.observe(el);
    return () => watch.disconnect();
  }, []);

  const n = series.length;
  const hasPrev = !!previous && previous.length > 0;
  const showPrev = hasPrev && !off.has("previous");
  const showViews = !off.has("views");
  const showVisitors = !off.has("visitors");
  const innerW = Math.max(40, width - PAD.left - PAD.right);
  const innerH = HEIGHT - PAD.top - PAD.bottom;

  const peak = Math.max(
    0,
    ...(showViews ? series.map((d) => d.views) : []),
    ...(showVisitors ? series.map((d) => d.visitors) : []),
    ...(showPrev && showViews ? previous.map((d) => d.views) : []),
    ...(showPrev && showVisitors ? previous.map((d) => d.visitors) : []),
  );
  const { max, ticks } = niceMax(peak);
  const x = (i: number) =>
    PAD.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH * (1 - v / max);
  const pts = (pick: (d: TimePoint) => number, rows: TimePoint[]) =>
    rows.map((d, i): [number, number] => [x(i), y(pick(d))]);
  const baseline = PAD.top + innerH;

  const line = (pick: (d: TimePoint) => number, rows: TimePoint[]) =>
    smoothPath(pts(pick, rows));
  const area = (pick: (d: TimePoint) => number, rows: TimePoint[]) => {
    const p = pts(pick, rows);
    const first = p[0];
    const last = p[p.length - 1];
    if (!first || !last) return "";
    return `${smoothPath(p)}L${last[0]},${baseline}L${first[0]},${baseline}Z`;
  };

  const toggle = (key: SeriesKey) => {
    const next = new Set(off);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setOff(next);
  };

  const at = (clientX: number, left: number, w: number) => {
    const rel =
      (clientX - left - (PAD.left * w) / width) / (innerW * (w / width));
    return Math.min(n - 1, Math.max(0, Math.round(rel * (n - 1))));
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (r.width === 0 || n === 0) return;
    setHover(at(e.clientX, r.left, r.width));
  };
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (n === 0) return;
    let next: number;
    if (e.key === "ArrowRight") next = Math.min(n - 1, (hover ?? -1) + 1);
    else if (e.key === "ArrowLeft") next = Math.max(0, (hover ?? n) - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = n - 1;
    else if (e.key === "Escape") {
      setHover(null);
      return;
    } else return;
    e.preventDefault();
    setHover(next);
    const d = series[next];
    if (d)
      setSpoken(
        `${dayLabel(d.date)}: ${d.visitors} visitors, ${d.views} page views`,
      );
  };

  const shown = hover === null ? null : (series[hover] ?? null);
  const before = hover === null || !hasPrev ? undefined : previous[hover];
  const hx = hover === null ? 0 : x(hover);
  const tipLeft = hx > width * 0.6;
  const xTicks =
    n <= 8
      ? Array.from({ length: n }, (_, i) => i)
      : Array.from(
          new Set([0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (n - 1)))),
        );
  const totals = {
    visitors: series.reduce((s, d) => s + d.visitors, 0),
    views: series.reduce((s, d) => s + d.views, 0),
  };

  return (
    <div className="tc" ref={box}>
      <div className="tc-legend" role="group" aria-label="Show or hide lines">
        <button
          type="button"
          className="tc-key tc-key-visitors"
          aria-pressed={showVisitors}
          onClick={() => toggle("visitors")}
        >
          Visitors <b>{totals.visitors}</b>
        </button>
        <button
          type="button"
          className="tc-key tc-key-views"
          aria-pressed={showViews}
          onClick={() => toggle("views")}
        >
          Page views <b>{totals.views}</b>
        </button>
        {hasPrev && (
          <button
            type="button"
            className="tc-key tc-key-previous"
            aria-pressed={showPrev}
            onClick={() => toggle("previous")}
          >
            Previous period
          </button>
        )}
      </div>
      <div
        className="tc-plot"
        role="group"
        aria-label={`${label}. Use the left and right arrow keys to read each day.`}
        tabIndex={0}
        onPointerMove={move}
        onPointerLeave={() => setHover(null)}
        onKeyDown={key}
        onBlur={() => setHover(null)}
      >
        <svg
          width={width}
          height={HEIGHT}
          viewBox={`0 0 ${width} ${HEIGHT}`}
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={`${uid}v`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--m-s1)" stopOpacity="0.38" />
              <stop offset="1" stopColor="var(--m-s1)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id={`${uid}p`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--m-s2)" stopOpacity="0.28" />
              <stop offset="1" stopColor="var(--m-s2)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line
                className={t === 0 ? "tc-base" : "tc-grid"}
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(t)}
                y2={y(t)}
              />
              <text
                className="tc-axis"
                x={PAD.left - 8}
                y={y(t) + 4}
                textAnchor="end"
              >
                {t}
              </text>
            </g>
          ))}
          {xTicks.map((i) => (
            <text
              key={i}
              className="tc-axis"
              x={x(i)}
              y={HEIGHT - 8}
              textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
            >
              {shortDay(series[i]?.date ?? "")}
            </text>
          ))}
          {showPrev && showViews && previous && (
            <path
              className="tc-prev tc-prev-views"
              d={line((d) => d.views, previous)}
            />
          )}
          {showPrev && showVisitors && previous && (
            <path
              className="tc-prev tc-prev-visitors"
              d={line((d) => d.visitors, previous)}
            />
          )}
          {showViews && (
            <>
              <path
                className="tc-area"
                fill={`url(#${uid}p)`}
                d={area((d) => d.views, series)}
              />
              <path
                className="tc-line tc-line-views"
                pathLength={1}
                d={line((d) => d.views, series)}
              />
            </>
          )}
          {showVisitors && (
            <>
              <path
                className="tc-area"
                fill={`url(#${uid}v)`}
                d={area((d) => d.visitors, series)}
              />
              <path
                className="tc-line tc-line-visitors"
                pathLength={1}
                d={line((d) => d.visitors, series)}
              />
            </>
          )}
          {shown && (
            <g>
              <line
                className="tc-cross"
                x1={hx}
                x2={hx}
                y1={PAD.top}
                y2={baseline}
              />
              {showViews && (
                <circle
                  className="tc-dot tc-dot-views"
                  cx={hx}
                  cy={y(shown.views)}
                  r={5}
                />
              )}
              {showVisitors && (
                <circle
                  className="tc-dot tc-dot-visitors"
                  cx={hx}
                  cy={y(shown.visitors)}
                  r={5}
                />
              )}
            </g>
          )}
        </svg>
        {shown && (
          <div
            className={`tc-tip${tipLeft ? " is-left" : ""}`}
            style={{ left: hx }}
            aria-hidden="true"
          >
            <strong>{dayLabel(shown.date)}</strong>
            {showVisitors && (
              <TipRow
                kind="visitors"
                name="Visitors"
                value={shown.visitors}
                compare={versus(
                  shown.visitors,
                  showPrev ? before?.visitors : undefined,
                )}
              />
            )}
            {showViews && (
              <TipRow
                kind="views"
                name="Page views"
                value={shown.views}
                compare={versus(
                  shown.views,
                  showPrev ? before?.views : undefined,
                )}
              />
            )}
          </div>
        )}
      </div>
      <p className="visually-hidden" aria-live="polite">
        {spoken}
      </p>
    </div>
  );
}

function TipRow({
  kind,
  name,
  value,
  compare,
}: {
  kind: "visitors" | "views";
  name: string;
  value: number;
  compare: { text: string; tone: string } | null;
}) {
  return (
    <span className={`tc-tip-row tc-tip-${kind}`}>
      <span>{name}</span>
      <b>{value}</b>
      {compare && (
        <i className={`tc-vs tc-vs-${compare.tone}`}>{compare.text}</i>
      )}
    </span>
  );
}
