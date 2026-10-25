# Operational readiness audit

Date: 25 Oct 2026. Phase 9 of the product-quality brief. This builds on the [security audit](security-audit-summary.md) (68 checks, closed on 25 Oct) and adds what that audit did not cover: background jobs, retention, migrations, backups, recovery and keep-warm. **Nothing was done to production and no production customer data was read.** Restore and migration rehearsals ran only on scratch PostgreSQL databases created for the purpose and deleted afterwards.

## Result

| Area | Status | In short |
|---|---|---|
| Security controls in the brief's list | Covered by the security audit | Table below, each with its tests |
| Background clean-up | **Defect found and fixed** | One failing step could stop all retention until a restart |
| Data retention | Verified | Matches the privacy notice, and now follows the plan that applies (see the subscription audit) |
| Migrations | Verified, 2 tests added | One head, every revision has a downgrade, a 3-step rollback and re-upgrade worked on PostgreSQL |
| Restore | Rehearsed locally | Dump, restore, start the app, sign in with the restored password hash: all worked |
| Backup schedule | **Open, needs an owner decision** | Backups are taken by hand |
| Keep-warm | Verified | Cron every 15 minutes and monitors every 5 minutes; process uptime 10.6 hours when checked |
| Email and webhook delivery | Partly ready | Failures are counted and shown; there is no retry queue and no alert |

## Defect fixed: one failed step stopped all retention

The hourly clean-up (`_maintenance_loop` in `main.py`) ran its steps one after another with no error handling. If any of them raised (a database that is still waking up is the realistic case on the free tier), the task ended and was never restarted: **no retention would run again until the next restart**. Because the service is deliberately kept warm, "until the next restart" can be weeks, which would break the retention promises in the privacy notice (scan history windows, 12-month audit log, 90-day visit statistics, expired sessions and invitations).

- **Fix:** each step now runs on its own; a failure is logged with its name and the next step still runs, and the loop continues to the next hour.
- **Tests:** `test_maintenance_loop.py`. One step that always fails does not stop the steps after it; a failed first pass is followed by working passes. Both tests fail if the error handling is removed (checked).

## Security items from the brief, and where each is covered

| Item | Evidence |
|---|---|
| Cross-customer isolation, workspace authorisation | `test_cross_customer`, `test_route_coverage`, `test_agency_roles`, `test_authentication_sweep` (a new route is private until someone lists it as public) |
| API-token permissions | `test_token_scope`, `test_integrations` |
| SSRF, DNS rebinding, redirect validation | `test_ssrf_matrix`, `test_fetcher`: every address form and every redirect is checked and pinned before a request is made |
| Scheduled-scan authorisation | `test_schedule_authorisation`; the scheduler re-checks plan and verification on every run |
| Account deletion and data export | `test_deletion_sweep`, `test_account_deletion_data`. Open: a live paid subscription is not cancelled (see the subscription audit) |
| Secrets, logging | `test_log_secrets`, `scripts/scan_secrets.py` in CI, startup guards for CORS and the placeholder database password |
| Rate limiting | `test_auth`, `test_scan_control`. Counters are in memory (security checklist items 34 and 53) |
| Dependency vulnerabilities | `pip-audit` and `npm audit` in the CI security job |
| Session security, error handling | `test_auth`, `test_error_responses` |

Nothing in the security audit's FAIL column; its six PARTIAL and two NOT VERIFIED items are unchanged by this phase.

## Retention

| Data | Kept | Where it is enforced |
|---|---|---|
| Scans, findings, reports | 30 / 90 / 365 days by plan | hourly loop, `delete_expired_history` |
| Audit log | 365 days (setting) | hourly loop |
| Visit statistics | 90 days (setting) | hourly loop |
| Expired sessions, sign-in states | removed hourly | hourly loop |
| Invitations | 30 days after expiry | hourly loop |
| Webhook delivery log | recent entries only | at write time |
| Database backups | Neon's short history window; your own dumps until you delete them | manual (see below) |

## Migrations

- **Start-up:** the container runs `python -m app.database.migrate` and then the server, so a migration error means the service does not start and Render keeps the previous version running.
- **Tests added** (`test_migration_chain.py`): exactly one head (two heads would break the start-up command) and a `downgrade` on every revision.
- **Rehearsal (scratch PostgreSQL 16):** fresh database to 0018; rolled back three revisions to 0015; upgraded again to 0018. Both directions worked.
- **Policy unchanged:** on production, do not roll a migration back by hand. Restore a backup taken before the release and deploy the previous code. The rehearsal shows rollback is mechanically possible, not that it is safe on live data.

## Restore rehearsal (scratch database, not production)

1. Fresh database at 0018, one account created through the API.
2. `pg_dump` custom format, then `pg_restore` into an empty database with `--exit-on-error`: no errors.
3. Migration command on the restored copy: no changes needed (0018).
4. Started the application on the restored copy: ready; signed in with the original password; the account and its workspace were present.

On 25 Oct the same procedure also passed on the production database copy on the owner's PC (28 tables, schema 0018; see `OPERATIONS.md`).

## Backups: open decision

Backups are taken by hand with `scripts/backup-db.ps1`. For a controlled pilot with a few users that is acceptable if it is done weekly and before every migration. A schedule needs a credential that can read production, so the choices are:

1. **Windows Task Scheduler on the owner's PC**, using a **read-only database role** created in Neon just for backups, with its connection string stored in a user-encrypted file. The PC must be on at that time.
2. **A scheduled GitHub Actions job.** Works while the PC is off, but puts a production database credential into GitHub and stores dumps as artifacts. Not recommended for a database holding password hashes.
3. **Neon's paid plan** with longer point-in-time restore: no scripts, costs money.

Recommendation: option 1 once the pilot has real users. I did not write a scheduling script, because it handles a production credential and cannot be tested here (it needs Windows, Docker and the real database). It should be written and tested together with the owner.

## Keep-warm

- A Cloudflare cron trigger calls `/api/v1/internal/run-due` every 15 minutes, and external monitors check `/health`, `/ready` and the site every 5 minutes.
- When checked, Platform Health showed an uptime of 10 hours 36 minutes (since the last deploy), 0 server errors in the last hour, and the run-due calls arriving.
- Cost to know: an always-warm free instance uses about 744 of Render's 750 free hours in a 31-day month, so a second service on the same account would run out of hours.
- Latency when checked: median 582 ms, p95 about 4.2 s (the API is in Oregon and the database in Frankfurt).

## Background jobs, email and webhooks

- **Scheduled scans:** due schedules are claimed with a compare-and-set update of `next_run_at`, so two overlapping cron calls cannot start the same scan twice; at most three jobs run per call.
- **Email:** sent counts, failures and the last failure are shown on Platform Health. Nothing alerts the owner when mail fails; check the page after releases.
- **Webhooks:** deliveries are recorded; a failed delivery is not retried (the retry queue is a queued feature). Alerts that matter should also arrive by email.
- **Scans interrupted by a restart** are marked failed on the next start, never shown as complete.

## Recovery steps (summary)

The full runbook is `OPERATIONS.md`. In short: bad code, revert and push; bad migration, restore the pre-release backup and deploy the previous code; lost database, create a new Neon database, restore the latest dump with `pg_restore --no-owner --no-privileges`, set `SECURESCOPE_DATABASE_URL` in Render, redeploy; after any restore, sign in, open Targets and Scan History, and run one scan of a verified site.

## Unresolved risks

1. No scheduled backup (owner decision above). Data loss window is the age of the latest dump plus Neon's short history.
2. One API instance, one database, one maintainer. Recovery by hand takes hours and has not been rehearsed on production, only on copies.
3. Rate-limit counters are in memory and reset on restart (security checklist items 34 and 53).
4. No retry for failed webhooks, no alert for failed email.
5. Migrations run under the runtime database role (checklist items 27 and 59).

## Statuses for this phase

- Local development: READY.
- Owned or authorised sites: READY WITH CONDITIONS.
- Controlled external pilot (free plans): READY WITH CONDITIONS: weekly manual backup, one API instance, and the owner checking Platform Health after each release.
- Public commercial launch: NOT READY (backup schedule, shared rate limits, separate database roles, webhook retry, billing).
