import { useEffect, useState } from "react";
import { ApiError, fetchActivation, fetchAnalytics } from "../api";
import { Kpi, Panel, trendOf } from "../components/charts";
import TimeChart from "../components/TimeChart";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import "../metrics.css";
import type {
  ActivationFunnel,
  AnalyticsCount,
  AnalyticsSummary,
} from "../types";

const RANGES = [7, 30, 90] as const;

const PAGE_LABEL: Record<string, string> = {
  home: "Home (signed out)",
  login: "Sign in",
  register: "Create account",
  "forgot-password": "Forgot password",
  "reset-password": "Reset password",
  "verify-email": "Confirm email",
  "sample-report": "Sample report",
  "agency-features": "Agency features",
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

export function duration(seconds: number | null): string {
  if (seconds === null) return "no completed scan yet";
  if (seconds < 90) return "under 2 minutes";
  if (seconds < 5400) return `${Math.round(seconds / 60)} minutes`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} hours`;
  return `${Math.round(seconds / 86400)} days`;
}

const FUNNEL_STEPS: { key: keyof ActivationFunnel; label: string }[] = [
  { key: "created", label: "Workspace created" },
  { key: "website_added", label: "Website added" },
  { key: "website_verified", label: "Website verified" },
  { key: "first_scan_completed", label: "First scan completed" },
  { key: "second_scan_completed", label: "Second scan completed" },
  { key: "monitoring_enabled", label: "Monitoring enabled" },
  { key: "report_downloaded", label: "Report downloaded" },
  { key: "api_token_created", label: "API token created" },
];

function Activation({ days }: { days: number }) {
  const [data, setData] = useState<ActivationFunnel | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchActivation(days)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [days]);
  return (
    <Panel title={`Activation, workspaces created in the last ${days} days`}>
      {failed && (
        <p className="muted small" role="status">
          The activation counts could not be loaded.
        </p>
      )}
      {!failed && data === null && <Loading label="Loading activation…" />}
      {data && (
        <>
          <p className="muted small">
            Counted from records that already exist; nothing extra is tracked
            and no person or site is shown. Scheduled and CI scans count as
            completed scans.
            {data.small_cohort &&
              " Fewer than five workspaces: treat these as examples, not a trend."}
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">
                Workspaces that reached each step
              </caption>
              <thead>
                <tr>
                  <th scope="col">Step</th>
                  <th scope="col" className="num">
                    Workspaces
                  </th>
                  <th scope="col" className="num">
                    Share of created
                  </th>
                </tr>
              </thead>
              <tbody>
                {FUNNEL_STEPS.map(({ key, label }) => {
                  const value = Number(data[key]);
                  return (
                    <tr key={key}>
                      <td>{label}</td>
                      <td className="num">{value}</td>
                      <td className="num">
                        {data.created > 0
                          ? `${Math.round((value / data.created) * 100)}%`
                          : "–"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="small">
            Median time from sign-up to first completed scan:{" "}
            <strong>{duration(data.median_seconds_to_first_scan)}</strong>
          </p>
        </>
      )}
    </Panel>
  );
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
  const total = items.reduce((sum, i) => sum + i.count, 0);
  return (
    <Panel title={title}>
      {items.length === 0 ? (
        <p className="muted small">Nothing in this period.</p>
      ) : (
        <ul className="bar-list">
          {items.map((i) => (
            <li key={i.name}>
              <div className="bar-line">
                <span>{label(i.name)}</span>
                <strong>
                  {i.count}
                  {total > 0 && (
                    <span className="bar-share">
                      {Math.round((i.count / total) * 100)}%
                    </span>
                  )}
                </strong>
              </div>
              <div className="bar-track" aria-hidden="true">
                <div
                  className="bar-fill"
                  style={{ width: `${(i.count / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function DailyChart({ data }: { data: AnalyticsSummary }) {
  const series = data.current.series;
  const total = `${data.current.visitors} visitors and ${data.current.views} page views in ${series.length} days`;
  return (
    <Panel title="Daily visitors and views">
      <TimeChart
        series={series}
        previous={data.previous.series}
        label={total}
      />
      <details className="trend-table">
        <summary className="small">Show as a table</summary>
        <div className="table-wrap">
          <table className="data-table">
            <caption className="visually-hidden">
              Visitors and views per day
            </caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col" className="num">
                  Visitors
                </th>
                <th scope="col" className="num">
                  Views
                </th>
              </tr>
            </thead>
            <tbody>
              {[...series].reverse().map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td className="num">{d.visitors}</td>
                  <td className="num">{d.views}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Panel>
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
    <div className="stack dash mx">
      <header className="dash-head">
        <div>
          <h1>Website analytics</h1>
          <p className="dash-sub">
            Visits to the public pages only (home, sign-in, registration, sample
            report, legal pages). Signed-in use of the app is not counted. No
            cookies, no stored IP addresses; visitors are counted with a one-way
            hash that changes every day, so a person returning on another day
            counts again.
          </p>
        </div>
        <div role="group" aria-label="Time range" className="segmented">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={r === days}
              onClick={() => setDays(r)}
            >
              {r} days
            </button>
          ))}
        </div>
      </header>
      {error && <ErrorNotice message={error} />}
      {loading && <Loading label="Loading analytics…" />}
      {data && (
        <>
          <p className="dash-meta" role="status">
            <i
              className={`meta-dot ${data.tracking_enabled ? "is-on" : "is-off"}`}
              aria-hidden="true"
            />
            <span>
              {data.tracking_enabled
                ? "Counting is on."
                : "Counting is switched off."}{" "}
              {data.last_event_at
                ? `Last visit recorded ${formatDate(data.last_event_at)}.`
                : "No visit has been recorded yet."}{" "}
              Days follow your time zone ({data.timezone}).
            </span>
          </p>
          {data.current.views === 0 && data.previous.views === 0 ? (
            <EmptyState title="No visits recorded yet">
              Visits appear here once someone opens a public page. Open the
              sign-in page in a private window to check that counting works.
            </EmptyState>
          ) : null}
          <ul className="dash-kpis" aria-label="Visitors">
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
              trend={trendOf(data.current.visitors, data.previous.visitors)}
              spark={data.current.series.map((d) => d.visitors)}
            />
            <Kpi
              tone="lime"
              label={`Page views, ${days} days`}
              value={data.current.views}
              note={change(data.current.views, data.previous.views)}
              trend={trendOf(data.current.views, data.previous.views)}
              spark={data.current.series.map((d) => d.views)}
            />
          </ul>
          <DailyChart data={data} />
          <Activation key={days} days={days} />
          <div className="dash-cols dash-cols-2">
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
