import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  fetchPlatformHealth,
  getFeedbackSummary,
  type FeedbackSummary,
} from "../api";
import { Flag, Kpi, Panel, Row, Rows } from "../components/charts";
import { Donut, Levels } from "../components/viz";
import { ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
import "../metrics.css";
import type { PlatformHealth } from "../types";

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return m % 60 === 0 ? `${h} h` : `${h} h ${m % 60} min`;
  return `${Math.floor(h / 24)} days ${h % 24} h`;
}

const ms = (value: number | null) => (value === null ? "–" : `${value} ms`);

/** Reasons the operator should look at the platform. Only things that were actually measured count. */
export function attention(h: PlatformHealth): string[] {
  const out: string[] = [];
  if (!h.database.ok) out.push("The database did not answer.");
  const { requests } = h;
  if (
    requests.error_rate !== null &&
    requests.requests >= 20 &&
    requests.error_rate > 0.05
  )
    out.push(
      `${Math.round(requests.error_rate * 100)}% of recent requests failed with a server error.`,
    );
  if (h.mail.delivering) {
    const failed = h.mail.last_failure_at;
    const ok = h.mail.last_success_at;
    if (failed && (!ok || failed > ok))
      out.push(
        `The last email send failed${h.mail.last_failure_status ? ` (provider answered ${h.mail.last_failure_status})` : ""}.`,
      );
  } else {
    out.push("Email is not being delivered (log-only mail mode).");
  }
  if (!h.configuration.trusted_proxy)
    out.push(
      "The trusted proxy secret is not set, so rate limits use the proxy's address.",
    );
  return out;
}

const TOPIC_LABEL: Record<string, string> = {
  general: "General",
  ease_of_use: "Ease of use",
  reports: "Reports",
  accuracy: "Accuracy of findings",
  pricing: "Plans and pricing",
  other: "Something else",
};

function FeedbackPanel() {
  const [summary, setSummary] = useState<FeedbackSummary | null>(null);
  useEffect(() => {
    let live = true;
    getFeedbackSummary()
      .then((next) => {
        if (live && next && typeof next.count === "number") setSummary(next);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  if (!summary) return null;
  const plans = Object.entries(summary.by_plan ?? {});
  return (
    <Panel title="Customer feedback" aside="private, from the Account page">
      {summary.count === 0 ? (
        <p className="muted small">No feedback has been submitted yet.</p>
      ) : (
        <>
          <p>
            <strong>{summary.average?.toFixed(1)}</strong> average from{" "}
            {summary.count} {summary.count === 1 ? "entry" : "entries"} (
            {[5, 4, 3, 2, 1]
              .map((n) => `${n}★ ${summary.by_rating[String(n)] ?? 0}`)
              .join(", ")}
            )
          </p>
          {plans.length > 0 && (
            <p className="muted small">
              By plan:{" "}
              {plans
                .map(
                  ([name, s]) => `${name} ${s.average.toFixed(1)} (${s.count})`,
                )
                .join(" · ")}
            </p>
          )}
          <ul className="plain-list">
            {summary.latest.map((f) => (
              <li key={f.updated_at + f.rating + (f.plan ?? "")}>
                <span className="muted small">
                  {f.rating}★ · {f.plan ?? "Team member"}
                  {f.category
                    ? ` · ${TOPIC_LABEL[f.category] ?? f.category}`
                    : ""}{" "}
                  · {formatDate(f.updated_at)}
                </span>
                <br />
                {f.message ?? <span className="muted">No comment.</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

export default function Health() {
  const [data, setData] = useState<PlatformHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [routeQuery, setRouteQuery] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);

  const load = useCallback(() => {
    fetchPlatformHealth()
      .then((health) => {
        setData(health);
        setError(null);
        setLoadedAt(new Date());
      })
      .catch((err: unknown) =>
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not load platform health.",
        ),
      );
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const problems = data ? attention(data) : [];
  const routes = useMemo(() => {
    const q = routeQuery.trim().toLowerCase();
    return (data?.requests.routes ?? []).filter(
      (r) =>
        (!errorsOnly || r.errors > 0) &&
        (q === "" || r.route.toLowerCase().includes(q)),
    );
  }, [data, routeQuery, errorsOnly]);
  return (
    <div className="stack dash mx">
      <header className="dash-head">
        <div>
          <h1>Platform health</h1>
          <p className="dash-sub">
            Measured by the API process itself. Request figures cover this
            process since it last started (free hosting restarts it when idle),
            so they begin again after every restart. Nothing here is estimated.
          </p>
        </div>
        <div className="dash-tools">
          {loadedAt && (
            <span className="dash-stamp">
              Updated {loadedAt.toLocaleTimeString()}. Refreshes every 30
              seconds.
            </span>
          )}
          <button type="button" className="btn-ghost" onClick={load}>
            Refresh
          </button>
        </div>
      </header>
      {error && <ErrorNotice message={error} />}
      {!data && !error && <Loading label="Loading platform health…" />}
      {data && (
        <>
          <section
            className={`status-banner ${problems.length ? "is-warn" : "is-ok"}`}
            role="status"
            aria-label="Overall status"
          >
            <span className="status-dot" aria-hidden="true" />
            <div>
              <h2>
                {problems.length ? "Needs attention" : "No problems detected"}
              </h2>
              {problems.length ? (
                <ul>
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              ) : (
                <p>
                  The database answers, recent requests are succeeding and email
                  is being delivered.
                </p>
              )}
            </div>
          </section>
          <ul className="dash-kpis" aria-label="Key figures">
            <Kpi
              tone="cyan"
              label="Database"
              value={data.database.ok ? "Reachable" : "Down"}
              note={
                data.database.latency_ms === null
                  ? undefined
                  : `answered in ${data.database.latency_ms} ms`
              }
            />
            <Kpi
              tone="green"
              label="Uptime"
              value={duration(data.uptime_seconds)}
              note={`since ${formatDate(data.started_at)}`}
            />
            <Kpi
              tone="pink"
              label="Server error rate"
              value={
                data.requests.error_rate === null
                  ? "–"
                  : `${(data.requests.error_rate * 100).toFixed(1)}%`
              }
              note={`${data.requests.server_errors} of ${data.requests.requests} requests, last ${duration(data.requests.window_seconds)}`}
            />
            <Kpi
              tone="violet"
              label="Latency p95"
              value={ms(data.requests.p95_ms)}
              note={`median ${ms(data.requests.p50_ms)}, p99 ${ms(data.requests.p99_ms)}`}
            />
          </ul>
          <div className="dash-cols dash-cols-2">
            <Panel title="Request latency" aside="milliseconds">
              {data.requests.p50_ms === null ||
              data.requests.p95_ms === null ||
              data.requests.p99_ms === null ? (
                <p className="muted small">No requests measured yet.</p>
              ) : (
                <Levels
                  label={`Latency: median ${data.requests.p50_ms} ms, p95 ${data.requests.p95_ms} ms, p99 ${data.requests.p99_ms} ms`}
                  unit="ms"
                  levels={[
                    { label: "Median", value: data.requests.p50_ms },
                    { label: "p95", value: data.requests.p95_ms },
                    { label: "p99", value: data.requests.p99_ms },
                  ]}
                />
              )}
            </Panel>
            <Panel
              title={`Scan outcomes, last ${data.scans.window_hours} hours`}
            >
              <Donut
                label={`Scans by outcome: ${data.scans.completed} completed, ${data.scans.failed} error, ${data.scans.cancelled} cancelled, ${data.scans.in_progress} running`}
                total={
                  data.scans.completed +
                  data.scans.failed +
                  data.scans.cancelled +
                  data.scans.in_progress
                }
                unit="scans"
                parts={[
                  {
                    label: "Completed",
                    value: data.scans.completed,
                    tone: "good",
                  },
                  { label: "Error", value: data.scans.failed, tone: "bad" },
                  {
                    label: "Cancelled",
                    value: data.scans.cancelled,
                    tone: "warn",
                  },
                  {
                    label: "Running",
                    value: data.scans.in_progress,
                    tone: "info",
                  },
                ]}
              />
            </Panel>
          </div>
          <div className="dash-cols dash-cols-3">
            <Panel title={`Scans, last ${data.scans.window_hours} hours`}>
              <Rows>
                <Row label="Completed">{data.scans.completed}</Row>
                <Row label="Ended in an error">{data.scans.failed}</Row>
                <Row label="Cancelled">{data.scans.cancelled}</Row>
                <Row label="Queued or running now">
                  {data.scans.in_progress}
                </Row>
                <Row label="Average duration">
                  {data.scans.avg_seconds === null
                    ? "–"
                    : `${data.scans.avg_seconds.toFixed(1)} s`}
                </Row>
                <Row label="Parallel scan limit">
                  {data.scans.running_here} of {data.scans.max_concurrent} slots
                  in use
                </Row>
              </Rows>
              <p className="panel-note">
                From the database; scans you delete or that age out are not
                counted.
              </p>
            </Panel>
            <Panel title="Email">
              <Rows>
                <Row label="Provider">{data.mail.provider}</Row>
                <Row label="Sent since start">{data.mail.sent}</Row>
                <Row label="Failed since start">{data.mail.failed}</Row>
                <Row label="Last success">
                  {data.mail.last_success_at
                    ? formatDate(data.mail.last_success_at)
                    : "none yet"}
                </Row>
                <Row label="Last failure">
                  {data.mail.last_failure_at
                    ? formatDate(data.mail.last_failure_at)
                    : "none"}
                </Row>
              </Rows>
            </Panel>
            <Panel title="Configuration">
              <Rows>
                <Row label="Trusted proxy secret">
                  <Flag
                    on={data.configuration.trusted_proxy}
                    yes="set"
                    no="not set"
                  />
                </Row>
                <Row label="Secure cookies">
                  <Flag
                    on={data.configuration.cookie_secure}
                    yes="on"
                    no="off"
                  />
                </Row>
                <Row label="Visitor analytics">
                  <Flag
                    on={data.configuration.analytics_enabled}
                    yes="on"
                    no="off"
                  />
                </Row>
                <Row label="/metrics endpoint">
                  <Flag
                    on={data.configuration.metrics_endpoint}
                    yes="enabled"
                    no="off"
                  />
                </Row>
                <Row label="Ownership proof valid">
                  {data.configuration.verification_valid_days === 0
                    ? "never expires"
                    : `${data.configuration.verification_valid_days} days`}
                </Row>
                <Row label="Scan retention (Free plan)">
                  {data.configuration.retention_days} days
                </Row>
                <Row label="Version">{data.version}</Row>
              </Rows>
            </Panel>
          </div>
          <Panel title="Busiest routes" aside="since the last restart">
            {data.requests.routes.length === 0 ? (
              <p className="muted small">No requests measured yet.</p>
            ) : (
              <>
                <div className="table-tools">
                  <input
                    className="input"
                    type="search"
                    placeholder="Filter routes"
                    aria-label="Filter routes"
                    value={routeQuery}
                    onChange={(e) => setRouteQuery(e.target.value)}
                  />
                  <button
                    type="button"
                    className="chip"
                    aria-pressed={errorsOnly}
                    onClick={() => setErrorsOnly(!errorsOnly)}
                  >
                    Errors only
                  </button>
                  <span className="muted small" role="status">
                    Showing {routes.length} of {data.requests.routes.length}
                  </span>
                </div>
                <div className="table-wrap">
                  <table className="data-table">
                    <caption className="visually-hidden">
                      Requests per route since the last restart
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Route</th>
                        <th scope="col" className="num">
                          Requests
                        </th>
                        <th scope="col" className="num">
                          Errors
                        </th>
                        <th scope="col" className="num">
                          p95
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {routes.map((r) => (
                        <tr key={r.route}>
                          <td className="route">{r.route}</td>
                          <td className="num">{r.requests}</td>
                          <td className="num">{r.errors}</td>
                          <td className="num">{ms(r.p95_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Panel>
          <FeedbackPanel />
        </>
      )}
    </div>
  );
}
