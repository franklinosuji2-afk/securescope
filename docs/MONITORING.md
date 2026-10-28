# Platform health and metrics

Operator-only. Everything is measured by the API process itself; nothing is estimated or sampled from
another system.

## Platform health page
Left menu, **Platform health** (same operator account as Analytics: confirmed email equal to
`SECURESCOPE_ADMIN_EMAIL`; everyone else gets `404`). Data comes from `GET /api/v1/platform/health`.

| Section | Source |
| --- | --- |
| Database reachable and answer time | a trivial query run when the page loads |
| Uptime | process start time |
| Server error rate, p50/p95/p99 latency, busiest routes | requests handled in the last hour by this process (probes `/health`, `/ready` and `/metrics` are excluded) |
| Scans, last 24 hours | the `scans` table: completed, ended in an error, cancelled, queued or running, average duration |
| Email | counters kept by the mailer since start: sent, failed, last success, last failure and provider status code |
| Configuration | booleans only (secret set or not); never values |

The page flags **Needs attention** only for measured conditions: database down, more than 5% server
errors once at least 20 requests exist, the latest email send having failed, log-only mail mode, or no
trusted proxy secret.

### Limits
- Request and mail figures live in memory. They restart from zero on every restart or wake-up (free
  hosting sleeps when idle) and cover one process only. Use a Prometheus scrape (below) for history.
- Route labels are templates such as `/api/v1/scans/{scan_id}`, never raw URLs, so identifiers and
  tokens never appear in metrics.
- "Ended in an error" includes scans that failed because the target was unreachable, not only faults
  in SecureScope.

## `/metrics` (Prometheus text format)
Off unless `SECURESCOPE_METRICS_TOKEN` is set (then `404`). Request with
`Authorization: Bearer <token>`; a missing or wrong token gives `401`. The endpoint is on the API host
itself (for example `https://<api-origin-host>/metrics`), not through the Cloudflare
Worker, which forwards only `/api/*`.

Exposed series: `securescope_up`, `securescope_process_start_time_seconds`, `securescope_database_up`,
`securescope_database_ping_seconds`, `securescope_http_requests_total{method,route,status}`,
`securescope_http_request_duration_seconds` (histogram), `securescope_scans_24h{status}`,
`securescope_scans_running_here`. No emails, tokens or hostnames are exported.

Create the token yourself (a password manager's generator works, 40+ characters), set it on Render as
`SECURESCOPE_METRICS_TOKEN`, and never paste it into chat or commit it.

### Optional: local Prometheus and Grafana
Not required and not deployed. To try it on your own machine, a `prometheus.yml` scrape job:

```yaml
scrape_configs:
  - job_name: securescope
    scheme: https
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/securescope.token   # a file containing only the token
    static_configs:
      - targets: ["<api-origin-host>"]
```

Useful starting queries: error ratio
`sum(rate(securescope_http_requests_total{status="5xx"}[5m])) / sum(rate(securescope_http_requests_total[5m]))`,
p95 latency
`histogram_quantile(0.95, sum by (le) (rate(securescope_http_request_duration_seconds_bucket[5m])))`.
A free Render service sleeps when idle, so a scrape may wake it; scrape no more often than every few
minutes.
