# Product improvement audit (Phase 0)

Date: 25 October 2026. Code at `7033eef` (CI green: security, frontend, backend on PostgreSQL 18, e2e, docker).
Labels: **Verified** (seen in the code or a test that was run), **Risk** (needs checking), **Recommendation**, **Not tested**.
Several audits already exist and are kept up to date rather than duplicated: `PROJECT_AUDIT.md` (v0.1 baseline),
`securescope-feature-audit.md`, `ENGINEERING_COVERAGE_AUDIT.md`, `SECURITY_VERIFICATION.md`, `release-readiness-report.md`,
`legal-audit.md`, `KNOWN_LIMITATIONS.md`, `SCORING_AND_SEVERITY.md`, `ROADMAP.md`. This file is the index and the plan input.

## 1. Repository architecture (Verified)
- Backend `backend/app`: FastAPI, SQLAlchemy 2, Alembic (19 migrations, `alembic/versions`), PostgreSQL in production (Neon), SQLite for local use. Layers: `api/v1` routes, `repositories`, `services`, `scanner`, `reporting`, `security`, `billing`.
- Frontend `frontend/src`: React 19, TypeScript strict, Vite, hand-written CSS, hash routing (`router.ts`), 19 pages, no UI library.
- Scans run as asyncio tasks inside the API process (`scanner/runner.py`); limits are in memory (`middleware/ratelimit.py`). Scheduled scans are triggered by a Cloudflare cron calling `/api/v1/internal/run-due` (`docs/OPERATIONS.md`).
- Deployment (not changed here): Render (API, Docker), Cloudflare Worker/Pages (site and cron), Neon (database), a mail API (Brevo or Resend).
- Commands (documented in `README.md`, `docs/TESTING.md`): backend `pytest`, `ruff check .`, `mypy app`, `bandit`; frontend `npm test`, `lint`, `typecheck`, `build`, `npx playwright test`; migrations run on start (`app/database/migrate.py`).

## 2. Verified existing capabilities (each has tests that pass)
Passive scanner with 40 documented rules (`frontend/src/guidance.json`); scoring (`scanner/scoring.py`); reports in HTML, Markdown, JSON, CSV and PDF; scan history and comparison; ownership verification by DNS TXT or file with 180-day expiry; accounts, email verification, password reset, Google/GitHub sign-in, device list, data export, deletion; teams with four roles; agency clients, branding and expiring share links; scheduled scans; email, webhook and Slack alerts with delivery history; API tokens and GitHub Action; score badges; plan limits; private feedback; audit log with 12-month retention.
Evidence: 934 backend tests, 218 frontend tests, 106 browser tests, all run in this review; security claims in `SECURITY_VERIFICATION.md`.

## 3. Partially implemented
- **Resolved findings:** "No longer detected" is set automatically by a later scan; there is no way to confirm a fix on demand (`repositories/scans.py::_record_states`, `ROADMAP.md`). *Verify fix* is the next change.
- **Scan comparison:** compares finding lists only; it does not say when two scans are not comparable because a check could not run (`reporting/compare.py`).
- **Agency:** clients and per-site assignment exist; reports are per scan, not per client; no per-client permissions (`api/v1/agency.py`).
- **Billing:** tables and plan rule exist (`billing/lifecycle.py`), nothing writes them until a provider is connected. Paid plans are correctly shown as "Coming soon".
- **PDF:** works, no cover page or executive summary layout yet.
- **Analytics:** cookieless page-view counter for public pages only (`tracking.ts`, `docs/ANALYTICS.md`); no product-activation events.

## 4. Missing
Per-rule positive/negative/edge tests for all 40 rules; scheduled report emails; client-level reports; retry queue for failed webhook deliveries; documented public API beyond `/ci`; backups on a schedule; load tests; a single real-browser test of the whole new-user journey; changelog and tagged releases.

## 5. Security-sensitive areas (all reviewed in `SECURITY_VERIFICATION.md` and `release-readiness-report.md`)
Cross-customer isolation (every id route is attacked as another customer; a guard test fails for a new one), outbound requests (one validate-and-pin path), API tokens, scheduled jobs, account deletion, subscriptions. Open: live subscription is not cancelled on account deletion (P1, needs a provider).

## 6. Test coverage and results (run for this audit)
Backend 934 passed (PostgreSQL 16 here, 18 in CI); frontend 218 passed; browser 106 passed; ruff, mypy, bandit, secret scan clean. Skipped tests: none locally; four files skip themselves without `bash/jq/curl`, `openssl`, a git checkout or PostgreSQL, all present in CI (skip counts in the CI log could not be read: **Not tested**). Gaps: per-rule tests; load; a real-socket webhook delivery test.

## 7. User-experience problems
- **Verified:** Scan History and Targets have no search or filter (`pages/History.tsx`, `pages/Targets.tsx`); fine at today's plan sizes (Agency allows 20 sites) but will not scale. Findings has search, severity, category, status and sort (`pages/Findings.tsx`).
- **Verified:** Overview shows at most 6 sites (`repositories/scans.py::overview(max_sites=6)`), with no link that lists all sites with their last-scan and next-scheduled dates.
- **Risk:** first request after the free host sleeps is slow; no wake-up message is shown. *Not tested* on the live site in this audit.
- **Risk:** nothing guides a new user from "verified" to "first scan" besides the Setup guide; not measured.

## 8. Performance (evidence)
- **Verified and fixed in this batch:** the scan-history list ran one extra query per scan (11 queries for 6 scans, about 30 for a page of 25). Fixed with one eager load; regression test `test_the_scan_list_costs_the_same_number_of_queries_for_a_big_page_as_for_a_small_one` fails without the fix (12 vs 6) and passes with it. The overview endpoint uses 7 queries for 6 scans.
- **Verified:** the frontend bundle is 497 KB (143 KB gzipped) in one JS file; fonts are self-hosted. No route-level code splitting. *Recommendation:* split only if page-load data shows a problem.
- **Verified:** polling: scan view polls while a scan runs (`useScan.ts`), the update check runs on an interval, the Health page every 30 s. Nothing excessive found.
- **Not tested:** behaviour under load (no load tests).

## 9. Operational risks
Backups only by hand (Neon free restore window is short); limits and running-scan list live in process memory (single instance only); cold starts; mail delivery on the live site unverified; Cloudflare rate-limit rule not set; Render in the US (see `legal-audit.md`). Details: `release-readiness-report.md` section 6.

## 10. Recommended improvements (priority)
| P | Change | Why / evidence |
|---|--------|----------------|
| P0 | none open | No result that overstates security was found; reports and legal text carry the passive-check limits (`reporting/reports.py`, `pages/Legal.tsx`). |
| P1 | Verify fix + "no longer detected" vs "confirmed resolved" | Today a fix cannot be confirmed without a full new scan. |
| P1 | Per-rule scanner tests and a scanner test matrix | 40 rules, 4 covered only as a group (`test_tls.py`). |
| P1 | Scan comparison says when two scans are not comparable | Avoids false "resolved" impressions. |
| P1 | Real-browser journey test; check live mail delivery | Pilot blocker. |
| P2 | Premium PDF cover/executive summary; client-level reports; sites list with filters | Agency value. |
| P2 | Retry queue for webhook deliveries; keep-warm | Reliability. |
| P2 | Activation events (privacy reviewed) | Cannot measure activation today. |
| P3 | Dark editorial redesign; public API docs; changelog | Later. |

## 11. Dependencies and blockers
Paddle approval blocks anything billing. The mail provider key and sending domain block the pilot journey. A lawyer's review and the transfer decision block paid launch (owner). Nothing else blocks engineering work.

## 12. Proposed order
1. Fix the scan-list N+1 (done in this batch).
2. Verify fix and resolved-state wording.
3. Scanner accuracy audit and per-rule test matrix; comparison "not comparable" notice.
4. Report consistency across formats and the PDF cover.
5. Portfolio view (all sites, last scan, next scheduled scan) with filters.
6. Agency client-level report.
7. Webhook retry queue; keep-warm; load test.
8. Activation analytics after a privacy review.
Each in its own small patch, with tests, nothing deployed without approval.
