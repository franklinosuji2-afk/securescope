import { useEffect, useState } from "react";
import { ApiError, fetchAnalytics } from "../api";
import { DailyHistogram, Kpi } from "../components/charts";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import type { AnalyticsCount, AnalyticsSummary } from "../types";

const RANGES = [7, 30, 90] as const;

const PAGE_LABEL: Record<string, string> = {
  home: "Home (signed out)",
  login: "Sign in",
  register: "Create account",
  "forgot-password": "Forgot password",
  "reset-password": "Reset password",
  "verify-email": "Confirm email",
  impressum: "Impressum",
  privacy: "Privacy notice",
  terms: "Terms",
};

export function change(current: number, previous: number): string {
  if (previous === 0) return current === 0 ? "no change" : "no earlier data";
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct === 0) return "no change";
  return `${pct > 0 ? "+" : ""}${pct}% vs previous period`;
}

function Bars({
  title,
  items,
  label = (n: string) => n,
}: {
  title: string;
  items: AnalyticsCount[];
  label?: (name: string) => string;
}) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <section className="card an-list">
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p className="muted small">Nothing in this period.</p>
      ) : (
        <ul>
          {items.map((i) => (
            <li key={i.name}>
              <div className="an-row">
                <span>{label(i.name)}</span>
                <strong>{i.count}</strong>
              </div>
              <div className="an-track" aria-hidden="true">
                <div
                  className="an-fill"
                  style={{ width: `${(i.count / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DailyChart({ data }: { data: AnalyticsSummary }) {
  const series = data.current.series;
  const total = `${data.current.visitors} visitors and ${data.current.views} page views in ${series.length} days`;
  return (
    <section className="card">
      <h2>Daily visitors and views</h2>
      <DailyHistogram series={series} label={total} />
      <p className="chart-legend">
        <span>Visitors</span>
        <span>Page views</span>
      </p>
      <details className="trend-table">
        <summary className="small">Show as a table</summary>
        <table className="small">
          <caption className="visually-hidden">
            Visitors and views per day
          </caption>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Visitors</th>
              <th scope="col">Views</th>
            </tr>
          </thead>
          <tbody>
            {[...series].reverse().map((d) => (
              <tr key={d.date}>
                <td>{d.date}</td>
                <td>{d.visitors}</td>
                <td>{d.views}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export default function Analytics() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  useEffect(() => {
    let cancelled = false;
    fetchAnalytics(days, timezone)
      .then((summary) => {
        if (cancelled) return;
        setData(summary);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof ApiError
              ? err.message
              : "Could not load the analytics.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [days, timezone]);

  const loading = data === null && error === null;
  return (
    <div className="stack dash">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Website analytics</h1>
        <div role="group" aria-label="Time range" className="row">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={r === days ? "btn" : "btn-ghost"}
              aria-pressed={r === days}
              onClick={() => setDays(r)}
            >
              {r} days
            </button>
          ))}
        </div>
      </div>
      <p className="muted small">
        Visits to the public pages only (sign-in, registration, legal pages).
        Signed-in use of the app is not counted. No cookies, no stored IP
        addresses; visitors are counted with a one-way hash that changes every
        day, so a person returning on another day counts again.
      </p>
      {error && <ErrorNotice message={error} />}
      {loading && <Loading label="Loading analytics…" />}
      {data && (
        <>
          <p className="muted small" role="status">
            {data.tracking_enabled
              ? "Counting is on."
              : "Counting is switched off."}{" "}
            {data.last_event_at
              ? `Last visit recorded ${formatDate(data.last_event_at)}.`
              : "No visit has been recorded yet."}{" "}
            Days follow your time zone ({data.timezone}).
          </p>
          {data.current.views === 0 && data.previous.views === 0 ? (
            <EmptyState title="No visits recorded yet">
              Visits appear here once someone opens a public page. Open the
              sign-in page in a private window to check that counting works.
            </EmptyState>
          ) : null}
          <ul className="summary-grid" aria-label="Visitors">
            <Kpi
              tone="cyan"
              label="Visitors today"
              value={data.today.visitors}
              note={`${data.today.views} page views`}
            />
            <Kpi
              tone="violet"
              label="Visitors yesterday"
              value={data.yesterday.visitors}
              note={`${data.yesterday.views} page views`}
            />
            <Kpi
              tone="pink"
              label={`Visitors, ${days} days`}
              value={data.current.visitors}
              note={change(data.current.visitors, data.previous.visitors)}
            />
            <Kpi
              tone="lime"
              label={`Page views, ${days} days`}
              value={data.current.views}
              note={change(data.current.views, data.previous.views)}
            />
          </ul>
          <DailyChart data={data} />
          <div className="an-grid">
            <Bars
              title="Top pages"
              items={data.top_pages}
              label={(n) => PAGE_LABEL[n] ?? n}
            />
            <Bars
              title="Landing pages"
              items={data.landing_pages}
              label={(n) => PAGE_LABEL[n] ?? n}
            />
            <Bars title="Sources" items={data.sources} />
            <Bars title="Devices" items={data.devices} />
          </div>
        </>
      )}
    </div>
  );
}
