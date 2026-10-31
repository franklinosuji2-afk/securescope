# SecureScope

[![CI](https://github.com/franklinosuji2-afk/securescope/actions/workflows/ci.yml/badge.svg)](https://github.com/franklinosuji2-afk/securescope/actions/workflows/ci.yml)

> **Status: v0.11.** Accounts, organizations, roles, tenant isolation and domain-ownership verification (DNS TXT / HTTP file) are implemented; scans only run against verified domains. Findings have a lifecycle (open, accepted risk, false positive, resolved) and the dashboard leads with what to fix first. Service email (confirmation links, password resets, invitations) is sent through Brevo or Resend when one is configured; the default `log` mailer only writes to the server log. The public launch is not done yet: see `docs/securescope-prelaunch-checklist.md` and `docs/IMPLEMENTATION_PLAN.md`.

A passive web-application security **posture** scanner for sites you own or are authorized to test. It checks a handful of safe, non-exploitative signals, explains each finding with evidence and a fix, keeps scan history, and exports reports.

> **SecureScope is not a penetration test or a full vulnerability scanner.** A clean result is not proof of security. The score is a heuristic.

## Quick start

```bash
cp .env.example .env      # then edit POSTGRES_PASSWORD (PowerShell: Copy-Item .env.example .env)
docker compose up --build
# open http://localhost:8080 and create an account (use exactly this address: other origins are refused)
```

Requires Docker with Compose v2. No cloud account, no paid API. Data lives in PostgreSQL in a Docker volume; migrations run automatically on backend start.

The database is PostgreSQL 18, the same major version as production (Neon). If you started the stack earlier with PostgreSQL 16, the old `pgdata` volume is not reused: export anything you want to keep with `pg_dump` first, then run `docker compose down -v` and start again to get a fresh database.

## Screenshots

Captured from the running app against a real scan history of my own portfolio site (`cfo-dev.pages.dev`): it started at 80/B with four findings, and three were fixed and later marked **Resolved** by SecureScope when a newer scan no longer reported them. Account details are replaced with placeholders.

| Overview: what to fix first, score history                  | Findings with lifecycle status                                   |
| ----------------------------------------------------------- | ---------------------------------------------------------------- |
| ![Overview, dark theme](docs/screenshots/overview-dark.png) | ![Findings list, dark theme](docs/screenshots/findings-dark.png) |

| Finding detail (light theme)                                                                      | Overview (light theme)                                        |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| ![Resolved finding with evidence and fix, light theme](docs/screenshots/finding-detail-light.png) | ![Overview, light theme](docs/screenshots/overview-light.png) |

## What is implemented

| Area                                                                                                                                                                                                                       | Status                                                                                                                     |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| HTTPS usage and response metadata (status, content type, redirects, timing)                                                                                                                                                | Implemented                                                                                                                |
| Security headers: HSTS (HTTPS only), CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy                                                                                                                      | Implemented                                                                                                                |
| Disclosure headers: `Server` version detail, `X-Powered-By`                                                                                                                                                                | Implemented                                                                                                                |
| Webhook alerts: signed (HMAC-SHA256) JSON to up to three HTTPS addresses per workspace, same triggers as the alert email                                                                                                   | Implemented                                                                                                                |
| GitHub Action and revocable API tokens for CI (Professional and Agency); opt-in public score badge for verified sites (all plans), see `docs/INTEGRATIONS.md`                                                              | Implemented                                                                                                                |
| Page and DNS checks: mixed content, subresource integrity, CORS, robots.txt and sitemap.xml hints, SPF, DMARC, CAA, DNSSEC (main domains only)                                                                             | Implemented                                                                                                                |
| Cookie attributes: `Secure`, `HttpOnly`, `SameSite`                                                                                                                                                                        | Implemented                                                                                                                |
| Conservative directory-index signature in the returned page                                                                                                                                                                | Implemented                                                                                                                |
| Heuristic score and grade, severity breakdown, score history per site                                                                                                                                                      | Implemented                                                                                                                |
| Evidence on every finding (URL, HTTP status, which headers were seen) and a per-finding confidence (`high` = observed, `medium` = heuristic)                                                                               | Implemented                                                                                                                |
| Finding lifecycle per organization and host: open, accepted risk, false positive (set by analysts, with a note), resolved (set only when a later completed scan no longer reports it). Failed scans never resolve anything | Implemented                                                                                                                |
| Reports state what was checked, what passed and the limits of the scan                                                                                                                                                     | Implemented                                                                                                                |
| Scan history, retention cleanup (per plan: 30 / 90 / 365 days)                                                                                                                                                             | Implemented                                                                                                                |
| Report export: PDF, HTML, Markdown, JSON                                                                                                                                                                                   | Implemented                                                                                                                |
| Scan control: cancel a queued or running scan, scan any finished site again with one click (ownership and rate limits are checked again)                                                                                   | Implemented                                                                                                                |
| Audit log for owners and admins: API and page with filter and paging                                                                                                                                                       | Implemented                                                                                                                |
| Dashboard: Overview (guided setup, "fix this first", per-site posture and score history), Targets, Findings (filters, detail page with impact, evidence and fix), Scan history, Team, Audit log                            | Implemented                                                                                                                |
| Accessibility: light and dark themes, severity never shown by colour alone, keyboard-operable, automated axe checks in CI, mobile navigation menu                                                                          | Implemented. No manual screen-reader testing yet                                                                           |
| Domain targets with DNS TXT / HTTP-file ownership verification; scans refused for unverified hosts                                                                                                                         | Implemented. HTTP-file verification confirmed once end to end on a real domain; the DNS TXT path is tested with mocks only |
| Registration, login, logout, sessions (HttpOnly cookies + CSRF), Argon2id passwords                                                                                                                                        | Implemented                                                                                                                |
| Organizations, 5 roles enforced server-side, tenant-isolated scans, audit events                                                                                                                                           | Implemented                                                                                                                |
| Email verification / password reset flows                                                                                                                                                                                  | Implemented. Mail is sent only when a provider is configured; otherwise it goes to the server log                          |
| Scheduled rescans (daily or weekly) with alerts only for new problems or a score drop (Professional and Agency)                                                                                                            | Implemented                                                                                                                |
| Re-verification of site ownership after the verification period lapses                                                                                                                                                     | Implemented                                                                                                                |
| Signed-in devices list with sign-out of other sessions (Account page)                                                                                                                                                      | Implemented                                                                                                                |
| App Scanning (Early Access pilot, off by default): dependency manifests read in the browser, CI results from Semgrep and Gitleaks via the GitHub Action, OSV lookups behind `SECURESCOPE_APP_OSV_ENABLED`                  | Pilot only. See `docs/app-scanning-stage-1-runbook.md`                                                                     |

## Roadmap (not implemented)

- Outdated-software detection, full TLS configuration testing (cipher/protocol enumeration), optional OWASP ZAP integration
- Egress proxy for production DNS-rebinding defence

## Safety model (enforced server-side)

- A scan needs a verified target for the exact host (DNS TXT or `/.well-known` file), plus an explicit authorization acknowledgement.
- Only `http`/`https` on ports 80, 443, 8080, 8443; no embedded credentials.
- Hostnames are resolved and every address must be globally routable; loopback, private, link-local, reserved and multicast are rejected.
- The scanner connects to the **validated IP** (DNS pinning, with correct Host/SNI), re-validating on every redirect. Only same-site redirects are followed; HTTPS→HTTP downgrades and off-origin hops are not followed and are reported.
- Limits: redirects, timeout, response size, requests per scan, scan duration, concurrent scans, per-client and per-target rate limits.
- No exploit payloads, brute force, credential attacks, port scans or off-origin crawling. Page bodies are never stored.
- Containers run as non-root with read-only filesystem and dropped capabilities; security headers on API and UI; strict CORS; pinned dependencies.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md), [docs/DATA_RETENTION.md](docs/DATA_RETENTION.md), [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md), [docs/SCORING_AND_SEVERITY.md](docs/SCORING_AND_SEVERITY.md) and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## API

| Method | Path                                                   | Purpose                                                                                 |
| ------ | ------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| GET    | `/api/v1/health`                                       | Liveness                                                                                |
| GET    | `/api/v1/ready`                                        | Readiness (database reachable)                                                          |
| POST   | `/api/v1/scans`                                        | Start a scan: `{"url": "...", "authorization_confirmed": true}` → 202                   |
| GET    | `/api/v1/scans?limit=&offset=`                         | List scans                                                                              |
| GET    | `/api/v1/scans/{id}`                                   | Scan detail with findings                                                               |
| POST   | `/api/v1/scans/{id}/cancel`                            | Cancel a queued or running scan                                                         |
| POST   | `/api/v1/scans/{id}/retry`                             | Scan the same address again after a scan has finished (new scan) → 202                  |
| GET    | `/api/v1/scans/{id}/report?format=json\|md\|html\|pdf` | Export                                                                                  |
| GET    | `/api/v1/audit-events?limit=&offset=&event_type=`      | Audit log (owners and admins)                                                           |
| GET    | `/api/v1/overview`                                     | Per-site posture: latest score, change, open findings, score history, what to fix first |
| PATCH  | `/api/v1/findings/{fingerprint}`                       | Analyst triage: accepted risk, false positive, or reopen                                |

Scan endpoints require a signed-in user. Authentication, organization and member endpoints are in [docs/API.md](docs/API.md).

## Development

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && mypy app && pytest          # SQLite
# or on PostgreSQL:
SECURESCOPE_TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/test pytest
SECURESCOPE_DATABASE_URL=... python -m app.database.migrate
uvicorn app.main:create_app --factory --reload   # http://localhost:8000

# frontend
cd frontend && npm ci
npm run lint && npm run typecheck && npm test && npm run build
npm run dev                                       # http://localhost:5173, proxies /api to :8000
```

Tests need no internet: scanner integration tests run against a local mock server (the `SECURESCOPE_ALLOW_PRIVATE_TARGETS` switch exists only for that and must never be enabled in deployment).

Configuration is via `SECURESCOPE_*` environment variables; see `.env.example`.

## Layout

```
backend/   FastAPI app, scanner, SQLAlchemy/Alembic, tests (see docs/ARCHITECTURE.md)
frontend/  React + TypeScript + Vite dashboard, Vitest tests, nginx config
docs/      threat model, retention, limitations, release checklist
```

## Licence

Add a licence before publishing (none is chosen yet).
