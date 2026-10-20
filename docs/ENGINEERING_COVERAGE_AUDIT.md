# Engineering coverage audit (111 topics)
- **Audit date:** 2026-10-21
- **Commit audited:** `main` after the commit that added this audit, plus the operations runbook, backup scripts and incident template added the same day.
- **Method:** every row below was assigned by reading the code, configuration, tests and documentation in this repository. Where evidence is a path, it was opened. Nothing was inferred from installed dependencies or README headings. Cloud-provider behaviour that is not configured in this repository is not counted as implemented.
- **Not a checklist to maximise.** SecureScope is a small passive scanner on free hosting. Many topics are correctly Not applicable.
## Status meanings
- **Implemented and verified:** code exists and tests or reproducible evidence support the claim.
- **Partially implemented:** some meaningful part exists; the full concept is missing or unverified.
- **Not implemented:** nothing meaningful found (this can still be the right call).
- **Not applicable:** the concept does not fit SecureScope's current architecture; reason given.
## Summary
| Status | Count |
|---|---|
| Implemented and verified | 20 |
| Partially implemented | 39 |
| Not implemented | 21 |
| Not applicable | 31 |
| **Total** | **111** |

**Counting method:** coverage is calculated on the 80 applicable topics (111 minus 31 not applicable). "Implemented and verified" = 20/80 (25%); "implemented and verified" plus "partially implemented" = 59/80 (74%). The percentages are only a summary of the table; the table is the source of truth. They are not a quality score.

## Findings from the audit that need action
1. **Backups and disaster recovery (83, 84):** scripts and a runbook now exist, but no backup has been taken from the real database and no restore rehearsed. Do this once and record the date in `OPERATIONS.md`.
2. **Alerting (62):** still not configured. The runbook describes a free monitor on `/api/v1/ready`.
3. **Rollback and incidents (55, 109, 111):** now written down and templated, not yet rehearsed.
4. **Idempotency for scan creation (14)** and **durable scan queue (15):** a restart loses running scans, and the API can create duplicate scans on a double submit.
5. **Stale documentation corrected:** `KNOWN_LIMITATIONS.md` said the audit log had no API or UI; `GET /api/v1/audit-events` and the Audit page exist and are tested. The line was removed.
6. **Single-instance assumptions (46):** rate limits and metrics are in memory; horizontal scaling needs shared state first.
## Topic table
| # | Topic | Status | Relevance | Evidence | Notes |
|---|---|---|---|---|---|
| 1 | Rate Limiting | Implemented and verified | High | `backend/app/middleware/ratelimit.py`; used for auth, scan creation, targets, analytics; tests in `test_auth.py`, `test_scan_control.py`, `test_targets.py`, `test_analytics.py`, `test_api.py` | Sliding-window limiter, in memory, per process. Correct for the current single instance; not shared across instances (documented in KNOWN_LIMITATIONS). |
| 2 | Caching | Partially implemented | Medium | `main.py` sets `Cache-Control: no-store` on API responses; `frontend/public/_headers` sets long-lived caching on hashed assets | HTTP cache headers are set deliberately. There is no application-level cache (none needed at current scale). |
| 3 | Load Balancing | Not applicable | Low | Single backend instance (`render.yaml`, `docker-compose.yml`) | No second instance exists. State is in memory, so a load balancer would first need shared rate-limit and metrics state. |
| 4 | Reverse Proxies | Implemented and verified | High | `frontend/worker/index.js` (+ `index.test.js`), `frontend/nginx.conf`, `backend/app/tests/test_client_ip.py` | Cloudflare Worker proxies `/api/*` and proves the client IP with a shared secret; nginx serves the SPA in Compose. Client-IP trust is tested. |
| 5 | API Gateways | Partially implemented | Low | `frontend/worker/index.js` | The Worker is a thin forwarder. It does not authenticate, rate-limit or transform requests, so it is not a gateway in the full sense. |
| 6 | CI/CD | Implemented and verified | High | `.github/workflows/ci.yml` (lint, types, tests on Postgres, build, e2e + axe, security scans); Cloudflare build and Render `autoDeploy` on push | CI runs on every push. Deployment is automatic from `main`. |
| 7 | Docker | Implemented and verified | High | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` (non-root users, `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, healthchecks); CI job builds the images | Images are built in CI. A clean-checkout `docker compose up` run has not been recorded (KNOWN_LIMITATIONS). |
| 8 | Kubernetes | Not applicable | None | None | A single small service on free hosting. Kubernetes would add cost and operational burden with no benefit. |
| 9 | Service Discovery | Not applicable | None | Compose service DNS only (`db`, `backend`) | One service talks to one database; no dynamic discovery is needed. |
| 10 | Circuit Breakers | Not implemented | Low | None | Outbound calls (mail provider, scan targets) have timeouts but no breaker. A mail-provider outage is logged and does not fail the request. |
| 11 | Timeouts | Implemented and verified | High | `core/config.py` (`request_timeout_seconds`, `max_scan_seconds`, `mail_timeout_seconds`); `scanner/runner.py` `wait_for`; `tests/test_fetcher.py` | Per-request, per-scan and mail timeouts exist. The scan time limit covers the page fetch, the TLS check and the probes. |
| 12 | Retries | Partially implemented | Low | `api/v1/scans.py` `POST /{scan_id}/retry` | Only a user-triggered re-scan exists. There are no automatic retries of failed outbound calls. |
| 13 | Exponential Backoff | Not implemented | Low | None | No automatic retries, so nothing to back off. Add only together with automatic retries. |
| 14 | Idempotency | Not implemented | Medium | Only schema migrations are tested as idempotent (`test_db_and_reports.py::test_migrations_are_idempotent_and_create_schema`) | No idempotency keys on create endpoints; a double submit can create two scans. The scan form disables its button while a request is in flight (`ScanForm.tsx`), but the API does not deduplicate. |
| 15 | Message Queues | Not implemented | Low | Scans run as in-process asyncio tasks limited by a semaphore (`api/deps.py`, `scanner/runner.py`) | No durable queue. A restart loses queued/running scans. Acceptable at current scale; revisit if scans become long or numerous. |
| 16 | Pub/Sub | Not applicable | None | None | No component needs to broadcast events. |
| 17 | Event-Driven Architecture | Not applicable | None | None | Request/response plus one background task is sufficient. |
| 18 | Distributed Transactions | Not applicable | None | None | One database; local transactions only. |
| 19 | Saga Pattern | Not applicable | None | None | No multi-service workflow. |
| 20 | Dead Letter Queues | Not applicable | None | None | No queue, so no dead letters. |
| 21 | Cron Jobs | Partially implemented | Medium | `main.py` `_maintenance_loop` (hourly retention cleanup for scans and analytics) | In-process hourly loop only. There are no scheduled scans. The loop stops when the free instance sleeps. |
| 22 | WebSockets | Not applicable | None | None | Not needed. |
| 23 | Long Polling | Partially implemented | Low | `frontend/src/useScan.ts` polls a scan until it reaches a final state | Short interval polling, not long polling. Adequate for scans that last seconds. |
| 24 | Server-Sent Events | Not applicable | None | None | Polling is enough for current scan durations. |
| 25 | Database Indexing | Partially implemented | Medium | Indexes in `models/*.py` and migrations (e.g. `ix_scans_organization_id_created_at`, `ix_audit_events_organization_id_timestamp`) | Indexes exist for the main access paths. No query-plan check (`EXPLAIN`) has been run on production-sized data. |
| 26 | Query Optimization | Partially implemented | Low | List endpoints paginate (`limit`/`offset`); analytics summary computed in Python with a row cap | No profiling or slow-query review has been done. |
| 27 | N+1 Queries | Partially implemented | Low | None specific | Not audited. Flagged as a follow-up for list endpoints that load findings. |
| 28 | Connection Pooling | Partially implemented | Medium | `database/session.py` (SQLAlchemy default pool, `pool_pre_ping=True`) | Default pool settings are used and have not been tuned for Neon connection limits. |
| 29 | Read Replicas | Not applicable | None | None | Not needed at current load. |
| 30 | Sharding | Not applicable | None | None | Not needed. |
| 31 | Partitioning | Not applicable | None | None | Retention deletes old rows instead (`DATA_RETENTION.md`). |
| 32 | Replication | Not applicable | Low | Provided by the managed database (Neon), not configured in this repo | Out of the repository's control; not verified here. |
| 33 | Leader Election | Not applicable | None | None | Single instance. |
| 34 | CAP Theorem | Not applicable | None | None | Single database; no distributed data store to reason about. |
| 35 | Eventual Consistency | Not applicable | None | None | Single database with transactional writes. |
| 36 | Optimistic Locking | Not implemented | Low | None | No version columns. Finding status changes are last-write-wins. |
| 37 | Pessimistic Locking | Not implemented | Low | None (no `with_for_update` in the code) | Not currently needed. |
| 38 | Distributed Locks | Not applicable | None | None | Single instance. |
| 39 | Race Conditions | Partially implemented | Medium | `ScanRepository.mark_running`/`complete_scan` return false for a scan cancelled meanwhile; `tests/test_scan_control.py` | Cancel-versus-complete races are handled and tested. Other concurrent writes are not specifically tested. |
| 40 | Deadlocks | Not implemented | Low | None | No handling or tests. Transactions are short and touch few rows. |
| 41 | Memory Leaks | Partially implemented | Low | `middleware/ratelimit.py` drops empty keys; analytics summary capped at 200,000 rows | No profiling or long-running soak test. |
| 42 | Garbage Collection | Not applicable | None | Managed by the Python runtime | No custom handling needed. |
| 43 | Thread Safety | Partially implemented | Low | `observability/metrics.py` uses a `threading.Lock`; blocking DB work runs in `asyncio.to_thread` with per-call sessions | Reasoned, not stress-tested. |
| 44 | Backpressure | Partially implemented | Medium | `max_concurrent_scans` semaphore (`core/config.py`, `api/deps.py`); per-client and per-target scan rate limits (`scans_per_client_per_hour`, `scans_per_target_per_hour`) | Concurrency is bounded and requests are rate-limited. There is no queue-length limit. |
| 45 | Autoscaling | Not applicable | None | None | Free single instance. |
| 46 | Horizontal Scaling | Not implemented | Low | Documented as a limitation: in-memory limiters and metrics | The app cannot yet run as several instances without shared state. |
| 47 | Vertical Scaling | Not applicable | None | Platform plan choice | Not controlled in code. |
| 48 | CDN | Implemented and verified | Medium | `frontend/wrangler.jsonc` (static assets on Cloudflare); live site answers with `Server: cloudflare` | Static files are served from Cloudflare's network. |
| 49 | Edge Caching | Partially implemented | Low | `frontend/public/_headers` | Cache headers are set; edge cache behaviour has not been measured. |
| 50 | Cache Invalidation | Partially implemented | Low | Hashed asset names; `no-cache` on `index.html` and `sw.js` in `_headers` | Handled for static assets; no other caches exist. |
| 51 | Feature Flags | Partially implemented | Low | Settings toggles: `analytics_enabled`, `metrics_token`, `mail_provider` | Environment toggles only; no runtime flag system. |
| 52 | Blue-Green Deployment | Not implemented | Low | None | Render replaces the instance on deploy; no parallel environment. |
| 53 | Canary Releases | Not implemented | Low | None | Not needed for a single small deployment. |
| 54 | Rolling Deployments | Not applicable | Low | Platform behaviour (Render), not configured in this repo | Not verified here. |
| 55 | Rollbacks | Partially implemented | Medium | `docs/OPERATIONS.md` section 4 | Procedure written down (git revert, provider redeploy, restore for migrations). It has not been rehearsed. |
| 56 | Health Checks | Implemented and verified | High | `api/v1/__init__.py` `/health` and `/ready`; `tests/test_api.py::test_ready_reports_database_state`; Render `healthCheckPath`; Docker `HEALTHCHECK` | Present and tested. |
| 57 | Liveness & Readiness Probes | Partially implemented | Medium | `/health` (liveness) and `/ready` (database check) | The two endpoints exist and map to the concepts, but there are no Kubernetes-style probe definitions. |
| 58 | Monitoring | Implemented and verified | Medium | Platform Health page and `api/v1/monitoring.py`; `tests/test_platform_health.py`; `docs/MONITORING.md` | In-app view for one process; resets on restart (documented). |
| 59 | Logging | Implemented and verified | High | `core/logging.py` (JSON to stdout, request IDs in `main.py`) | Structured logs with a request ID. Whether any log line could contain sensitive data has not been audited. There is no log retention or shipping setup. |
| 60 | Distributed Tracing | Not implemented | Low | Only an `X-Request-ID` correlation header (`main.py`) | No spans or trace export. Not needed for a single service. |
| 61 | Metrics | Implemented and verified | Medium | `observability/metrics.py`; optional Prometheus `/metrics` behind a bearer token; `tests/test_platform_health.py` | In-memory, one process. |
| 62 | Alerts | Not implemented | Medium | Setup steps in `docs/OPERATIONS.md` section 1 | No alerting is configured yet. The runbook describes a free external monitor on `/api/v1/ready`; this row changes once it is set up. |
| 63 | SLOs | Not implemented | Low | None | No targets defined. |
| 64 | SLIs | Partially implemented | Low | Request counts, error rates and p95 latency exist in `observability/metrics.py` | The raw measurements exist; no SLI has been formally defined from them. |
| 65 | Error Budgets | Not implemented | Low | None | Depends on SLOs. |
| 66 | Observability | Partially implemented | Medium | Logs + metrics + request IDs + Platform Health page | Logs and metrics exist; no tracing and no persistent history. |
| 67 | Secrets Management | Partially implemented | High | Secrets as `SecretStr` settings (`core/config.py`), `sync: false` in `render.yaml`, `.env.example` placeholders; Trivy secret scan in CI | Secrets stay out of git and are loaded from the environment. No secret manager and no rotation procedure. |
| 68 | IAM | Partially implemented | Medium | Application roles and permissions: `security/permissions.py` (five roles), `tests/test_tenancy.py`, `tests/test_targets.py` | Application-level access control is enforced server-side and tested. Cloud IAM (Cloudflare, Render, Neon accounts) is outside the repo. |
| 69 | OAuth | Not implemented | Low | None | Email and password only. Social login is optional future work. |
| 70 | JWT Rotation | Not applicable | None | Sessions are server-side opaque tokens (`security/tokens.py`, `models/account.py`) | No JWTs are used. |
| 71 | TLS | Implemented and verified | High | Edge TLS by Cloudflare (live scan: TLS 1.3, valid certificate); scanner TLS analysis in `scanner/tls.py` with `tests/test_tls.py`; cookies `Secure` by default | The edge certificate is managed by Cloudflare. |
| 72 | Encryption at Rest | Partially implemented | Medium | Passwords hashed with Argon2id (`security/passwords.py`) | Disk encryption is the database provider's responsibility and is not verified here. |
| 73 | Encryption in Transit | Partially implemented | Medium | Browser to Cloudflare over TLS; Worker to API over HTTPS; example DB URL uses `sslmode=require` (`render.yaml`) | The database link is configured by the operator and not verified by a test. |
| 74 | WAF | Not implemented | Medium | None configured in this repo | Cloudflare's free managed rules have not been configured or reviewed. |
| 75 | DDoS Protection | Partially implemented | Low | Cloudflare edge (inherent); application rate limits | No tailored protection or testing. |
| 76 | CORS | Implemented and verified | High | `main.py` `CORSMiddleware` with explicit origins; `tests/test_api.py::test_cors_only_allows_configured_origins` | Only configured origins are allowed. |
| 77 | CSRF | Implemented and verified | High | `ss_csrf` cookie echoed in `X-CSRF-Token`; `tests/test_auth.py` | Double-submit token on state-changing requests. |
| 78 | SQL Injection | Implemented and verified | High | SQLAlchemy parameterised queries throughout; Bandit and Semgrep (OWASP rules) in CI | No raw string-built SQL found. There is no dedicated injection-payload test. |
| 79 | XSS | Implemented and verified | High | React escaping, no `dangerouslySetInnerHTML` in `frontend/src`; CSP in `_headers`; report escaping tests (`test_db_and_reports.py`, `test_pdf_report.py` use `<script>` payloads) | Covered in the UI and in HTML, Markdown and PDF reports. |
| 80 | SSRF | Implemented and verified | High | `security/target.py`, `scanner/fetcher.py`; `tests/test_target.py`, `tests/test_fetcher.py`, `tests/test_probes.py` | Private-range rejection, DNS-rebinding pinning, redirect revalidation, downgrade blocking. KNOWN_LIMITATIONS still recommends an egress proxy for production. |
| 81 | Database Migrations | Implemented and verified | High | `backend/alembic/versions/0001`..`0005`; migration test in `test_db_and_reports.py`; tests run on PostgreSQL in CI | Migrations run at startup. |
| 82 | Schema Versioning | Implemented and verified | Medium | Alembic revision chain; `alembic_version` table | Versioned and linear. |
| 83 | Disaster Recovery | Partially implemented | High | `docs/OPERATIONS.md` sections 3 and 7 | Recovery steps and honest targets are written. They have not been rehearsed against production. |
| 84 | Backups | Partially implemented | High | `scripts/backup-db.ps1`, `scripts/restore-test.ps1`, `docs/OPERATIONS.md` section 2; dump and restore commands tested on PostgreSQL 16 (identical row counts and schema version) | The PowerShell wrappers have not yet been run against your Neon database, and no backup schedule exists. Neon alone keeps a short restore window. |
| 85 | Failover | Not implemented | Low | None | Single instance and database. |
| 86 | Multi-Region Deployment | Not applicable | None | None | Not justified at this scale. |
| 87 | Chaos Engineering | Not applicable | None | None | Out of scope for current maturity. |
| 88 | Cost Optimization | Partially implemented | Medium | Free-tier architecture documented in `docs/DEPLOY_FREE.md` | Designed for about zero cost. No cost monitoring. |
| 89 | Cold Starts | Partially implemented | Medium | Documented in `observability/metrics.py` and MONITORING.md (free instance sleeps) | Known and documented; no mitigation such as a keep-alive. |
| 90 | Serverless Limits | Partially implemented | Low | Cloudflare Worker is used only as a thin proxy; free-tier limits noted in DEPLOY_FREE.md | Limits are noted, not monitored. |
| 91 | Latency | Partially implemented | Medium | `response_time_ms` per scan; request latency in Platform Health | Measured in the app; no latency targets. |
| 92 | Throughput | Partially implemented | Low | Request counts in Platform Health | Counted, not load-tested. |
| 93 | P99 Latency | Not implemented | Low | Only p95 is computed (`observability/metrics.py`) | No p99. |
| 94 | Tail Latency | Not implemented | Low | None | Not analysed. |
| 95 | Network Partitions | Not applicable | None | None | No distributed state. |
| 96 | Clock Skew | Not applicable | None | None | Single node; expiry times use the server clock. |
| 97 | DNS | Partially implemented | High | DNS TXT ownership verification (`security/ownership.py`, `tests/test_targets.py`) and DNS validation in SSRF checks (`tests/test_target.py`) | DNS validation is tested. The TXT verification method has only been tested with mocked lookups; only the HTTP-file method has been run on a real domain (KNOWN_LIMITATIONS). |
| 98 | TCP vs UDP | Not applicable | None | All traffic is HTTP over TCP | No protocol choice is made in the code. |
| 99 | HTTP/2 & HTTP/3 | Partially implemented | Low | Negotiated by Cloudflare at the edge | Not configured or verified by the repo. |
| 100 | gRPC | Not applicable | None | None | REST/JSON only. |
| 101 | Webhooks | Not implemented | Low | None | No outbound or inbound webhooks. Possible future alert integration. |
| 102 | API Versioning | Implemented and verified | Medium | All routes under `/api/v1`; OpenAPI at `/api/v1/openapi.json` | A v2 path has never been needed. |
| 103 | Semantic Versioning | Partially implemented | Low | `0.1.0` in `backend/pyproject.toml` and `frontend/package.json` | Version numbers exist, but there are no tagged releases or changelog. |
| 104 | Infrastructure as Code | Partially implemented | Medium | `render.yaml`, `frontend/wrangler.jsonc`, `docker-compose.yml` | Service definitions are in git. DNS, Email Routing and Cloudflare settings are configured by hand. |
| 105 | Terraform | Not implemented | Low | None | Not needed for current scale. |
| 106 | Helm Charts | Not applicable | None | None | No Kubernetes. |
| 107 | Build Caching | Partially implemented | Low | pip/npm caching in CI (`cache: pip`, `cache: npm`); Docker layer ordering | No Docker layer cache in CI. |
| 108 | Dependency Hell | Implemented and verified | Medium | Pinned `requirements.txt`, `package-lock.json`; CI runs pip-audit, npm audit, Trivy | Worked as intended on 2026-10-20 when pip-audit flagged `certifi` and it was bumped. |
| 109 | Production Incidents | Partially implemented | Medium | `docs/OPERATIONS.md` section 6 | A basic response checklist exists; no incident has been recorded yet. |
| 110 | On-Call | Not applicable | Low | Single maintainer | Not meaningful for a solo project; revisit with a team. |
| 111 | Postmortems | Partially implemented | Low | `docs/INCIDENT_TEMPLATE.md`, `docs/incidents/` | Template exists; no postmortem has been written yet. |

## Evidence types
- **Code evidence:** paths in the Evidence column were read.
- **Documentation claims:** `DEPLOY_FREE.md`, `MONITORING.md` and `KNOWN_LIMITATIONS.md` are cited only where they describe the code accurately.
- **Unverified assumptions:** anything attributed to a hosting provider (Cloudflare, Render, Neon) is marked partial or not applicable, because it is not configured or tested here.

## Verification run for this audit
Run on 2026-10-21 against the working tree described above:

| Command | Result |
|---|---|
| `python -m pytest -q` (backend, SQLite and again on PostgreSQL 16) | all tests passed on both |
| `ruff check .`, `mypy app` | clean |
| `npm run lint`, `npm run typecheck`, `npm run format:check` | clean |
| `npx vitest run` | 96 passed |
| `npm run build` | built |
| `npx playwright test` (run earlier, same code apart from the dependency bump and `security.txt`) | 30 passed |
| `pg_dump` / `pg_restore` of a migrated database | identical row counts and schema version after restore |

Not run for this audit: `docker compose up`, the PowerShell backup scripts on Windows, any load test, and a restore of the real Neon database.
