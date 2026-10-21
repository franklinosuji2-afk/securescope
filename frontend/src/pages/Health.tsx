import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchPlatformHealth } from "../api";
import { ColumnChart, Kpi } from "../components/charts";
import { ErrorNotice, Loading } from "../components/ui";
import { formatDate } from "../format";
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

export default function Health() {
  const [data, setData] = useState<PlatformHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);

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
  return (
    <div className="stack dash">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Platform health</h1>
        <button type="button" className="btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>
      <p className="muted small">
        Measured by the API process itself. Request figures cover this process
        since it last started (free hosting restarts it when idle), so they
        begin again after every restart. Nothing here is estimated.
      </p>
      {error && <ErrorNotice message={error} />}
      {!data && !error && <Loading label="Loading platform health…" />}
      {data && (
        <>
          <section
            className={`card ${problems.length ? "notice-warn" : ""}`}
            role="status"
            aria-label="Overall status"
          >
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
              <p className="muted small">
                The database answers, recent requests are succeeding and email
                is being delivered.
              </p>
            )}
          </section>
          <ul className="summary-grid" aria-label="Key figures">
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
          <div className="an-grid">
            <section className="card">
              <h2>Request latency</h2>
              {data.requests.p50_ms === null ||
              data.requests.p95_ms === null ||
              data.requests.p99_ms === null ? (
                <p className="muted small">No requests measured yet.</p>
              ) : (
                <ColumnChart
                  unit="ms"
                  label={`Latency: median ${data.requests.p50_ms} ms, p95 ${data.requests.p95_ms} ms, p99 ${data.requests.p99_ms} ms`}
                  columns={[
                    {
                      label: "median",
                      value: data.requests.p50_ms,
                      tone: "cyan",
                    },
                    {
                      label: "p95",
                      value: data.requests.p95_ms,
                      tone: "violet",
                    },
                    { label: "p99", value: data.requests.p99_ms, tone: "pink" },
                  ]}
                />
              )}
            </section>
            <section className="card">
              <h2>Scan outcomes, last {data.scans.window_hours} hours</h2>
              <ColumnChart
                label="Scans by outcome"
                columns={[
                  {
                    label: "completed",
                    value: data.scans.completed,
                    tone: "green",
                  },
                  { label: "error", value: data.scans.failed, tone: "pink" },
                  {
                    label: "cancelled",
                    value: data.scans.cancelled,
                    tone: "amber",
                  },
                  {
                    label: "running",
                    value: data.scans.in_progress,
                    tone: "cyan",
                  },
                ]}
              />
            </section>
            <section className="card an-list">
              <h2>Scans, last {data.scans.window_hours} hours</h2>
              <ul>
                <li className="an-row">
                  <span>Completed</span>
                  <strong>{data.scans.completed}</strong>
                </li>
                <li className="an-row">
                  <span>Ended in an error</span>
                  <strong>{data.scans.failed}</strong>
                </li>
                <li className="an-row">
                  <span>Cancelled</span>
                  <strong>{data.scans.cancelled}</strong>
                </li>
                <li className="an-row">
                  <span>Queued or running now</span>
                  <strong>{data.scans.in_progress}</strong>
                </li>
                <li className="an-row">
                  <span>Average duration</span>
                  <strong>
                    {data.scans.avg_seconds === null
                      ? "–"
                      : `${data.scans.avg_seconds.toFixed(1)} s`}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Parallel scan limit</span>
                  <strong>
                    {data.scans.running_here} of {data.scans.max_concurrent}{" "}
                    slots in use
                  </strong>
                </li>
              </ul>
              <p className="muted small">
                From the database; scans you delete or that age out are not
                counted.
              </p>
            </section>
            <section className="card an-list">
              <h2>Email</h2>
              <ul>
                <li className="an-row">
                  <span>Provider</span>
                  <strong>{data.mail.provider}</strong>
                </li>
                <li className="an-row">
                  <span>Sent since start</span>
                  <strong>{data.mail.sent}</strong>
                </li>
                <li className="an-row">
                  <span>Failed since start</span>
                  <strong>{data.mail.failed}</strong>
                </li>
                <li className="an-row">
                  <span>Last success</span>
                  <strong>
                    {data.mail.last_success_at
                      ? formatDate(data.mail.last_success_at)
                      : "none yet"}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Last failure</span>
                  <strong>
                    {data.mail.last_failure_at
                      ? formatDate(data.mail.last_failure_at)
                      : "none"}
                  </strong>
                </li>
              </ul>
            </section>
            <section className="card an-list an-wide">
              <h2>Busiest routes</h2>
              {data.requests.routes.length === 0 ? (
                <p className="muted small">No requests measured yet.</p>
              ) : (
                <table className="small">
                  <caption className="visually-hidden">
                    Requests per route since the last restart
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Route</th>
                      <th scope="col">Requests</th>
                      <th scope="col">Errors</th>
                      <th scope="col">p95</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.requests.routes.map((r) => (
                      <tr key={r.route}>
                        <td style={{ overflowWrap: "anywhere" }}>{r.route}</td>
                        <td>{r.requests}</td>
                        <td>{r.errors}</td>
                        <td>{ms(r.p95_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
            <section className="card an-list">
              <h2>Configuration</h2>
              <ul>
                <li className="an-row">
                  <span>Trusted proxy secret</span>
                  <strong>
                    {data.configuration.trusted_proxy ? "set" : "not set"}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Secure cookies</span>
                  <strong>
                    {data.configuration.cookie_secure ? "on" : "off"}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Visitor analytics</span>
                  <strong>
                    {data.configuration.analytics_enabled ? "on" : "off"}
                  </strong>
                </li>
                <li className="an-row">
                  <span>/metrics endpoint</span>
                  <strong>
                    {data.configuration.metrics_endpoint ? "enabled" : "off"}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Ownership proof valid</span>
                  <strong>
                    {data.configuration.verification_valid_days === 0
                      ? "never expires"
                      : `${data.configuration.verification_valid_days} days`}
                  </strong>
                </li>
                <li className="an-row">
                  <span>Scan retention</span>
                  <strong>{data.configuration.retention_days} days</strong>
                </li>
                <li className="an-row">
                  <span>Version</span>
                  <strong>{data.version}</strong>
                </li>
              </ul>
            </section>
          </div>
          <p className="muted small">
            {loadedAt ? `Updated ${loadedAt.toLocaleTimeString()}. ` : ""}
            Refreshes every 30 seconds.
          </p>
        </>
      )}
    </div>
  );
}
