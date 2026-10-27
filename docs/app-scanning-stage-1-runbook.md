# App Scanning Stage 1 runbook: dormant deployment

Status: **prepared, not executed.** Nothing in this document has been run against production. No production database, configuration, flag or billing setting was touched while preparing it. Every "verified" below means: run on this repository, on a scratch database, on the date shown. It does not mean "safe in production".

Stage 1 deploys the App Scanning code with the feature **off**. It does not enable customer access, OSV lookups, notifications, billing or any new customer entitlement. A separate, explicit approval is required before the flag is ever turned on (section 10).

Date prepared: 26 Oct 2026. Release candidate (RC): see section 1; it is not final until the owner commits it.

---

## 0. Read this first: three facts that shape the procedure

1. **Migrations run when the API container starts.** `backend/Dockerfile` starts with `python -m app.database.migrate && exec uvicorn ...`. On Render there is no separate migration step: deploying the new code migrates the database (0021, 0022, 0023). "Back up first" is therefore mandatory, and "migrate" and "deploy" are the same event.
2. **A code-only rollback does not work after this release is live.** The previous release's container runs the same start command; its migration step stops with `Can't locate revision identified by '0023'` and the container does not start. Verified on a scratch database (section 8, evidence E5). Rollback is by one of two documented paths, not by redeploying the old image alone.
3. **Dormant does not mean inert.** The new code adds start-up work (a cleanup query on the new `app_scans` table, now wrapped so it cannot stop start-up) and a changed account-deletion routine that also deletes from the new tables. Both are covered by tests, listed below.

---

## 1. Pre-deployment checks

Do these in order. Record each result in the sign-off table (section 11).

### 1.1 Identify the exact release candidate

```
git status --short                 # must be empty (everything committed, nothing stray)
git log --oneline -1               # record this as the RELEASE ID
git diff 08e46d3 --stat            # 08e46d3 = last deployed state per this audit; review the file list
```

- 08e46d3 is the last commit before App Scanning work began (load-test batch). Confirm with the owner that it matches what is running in production today; if production runs something else, stop and re-assess compatibility.
- The RC must contain: batches 30 to 38 plus the Stage 1 additions (`backend/app/main.py` start-up guard, `backend/app/tests/test_appscan_stage1.py`, docs). **The Stage 1 additions were left uncommitted at the owner's instruction**; the owner commits them. Re-run section 1.4 on the final commit.

### 1.2 Review the migrations (0021, 0022, 0023)

0021 and 0022 only add tables. **0023 is different: it alters two existing tables** (`api_tokens` and `app_scans`), so read it separately, below the table.

0021 and 0022 are additive. Read them: `backend/alembic/versions/0021_app_scanning_tables.py` and `0022_app_findings.py`.

| Property | Finding | Evidence |
|---|---|---|
| Creates | `app_projects`, `app_scans`, `app_findings` and their indexes, only | `test_appscan_stage1.py::test_migrations_0021_and_0022_only_add_tables_and_change_nothing_that_exists` (column, index, foreign-key and unique-constraint snapshot of every pre-existing table is identical before and after) |
| Changes existing tables | None (no `ALTER`, no new column, no new constraint on existing tables) | Same test, plus `test_the_migration_files_contain_no_data_statements_jobs_or_destructive_operations` |
| Data statements, jobs, external calls | None in `upgrade()` | Same test (static check) |
| Locks on large tables | Creating new tables takes no lock on existing tables. Foreign keys *reference* `organizations` and `users`; on PostgreSQL that takes a brief share lock on those two small tables while the constraints are created | Reasoned from PostgreSQL behaviour; **not measured** on production data. Run section 3.2 and note the time |
| Existing data | Survives the upgrade unchanged | Same test inserts an organization at 0020 and reads it back after upgrade |
| Downgrade | Drops the three tables; restores the exact 0020 schema on a scratch database | Same test (snapshot equal to the 0020 schema after downgrade) |
| 0023 (token scope) | Adds `api_tokens.scope` (`NOT NULL`, server default `'web'`) and `api_tokens.expires_at` (nullable), and `app_scans.token_id` (nullable, foreign key to `api_tokens` `ON DELETE SET NULL`, with an index). Existing tokens become `web` tokens with no expiry: same behaviour, no App Scanning access. A token written by the previous release gets the default `web`. On PostgreSQL adding a column with a constant default does not rewrite the table; `api_tokens` is small (at most 5 rows per workspace) | `test_appscan_stage1.py::test_migration_0023_adds_scope_and_expiry_without_broadening_any_existing_token` (only `api_tokens` and `app_scans` differ; a legacy token reads back as `web`/no expiry) |
| 0023 and a code-only rollback | Code from before token scopes ignores `scope` and `expires_at`. App Scanning tokens therefore start with `ssa_`, a prefix that code accepts nowhere (it only accepts `ssk_`), so after a rollback without a downgrade an App token is simply unknown and cannot be used as a Web token | `test_web_tokens_keep_their_prefix_and_app_tokens_have_their_own`; reviewer finding T1 |
| 0023 downgrade | Restores the 0022 schema exactly. **It deletes `app`-scope tokens** (it never turns them into `web` tokens, which would broaden them). While the feature has never been on there are none | Same test |
| Destructive on rollback | **Yes, for App Scanning data only.** Downgrade deletes any rows in the three tables. While the feature has never been on, they hold no rows | Section 8.2 requires a row count of zero before using it |

### 1.3 Feature flag: default and enforcement

| Check | How it is proven | Result on 26 Oct 2026 |
|---|---|---|
| Default is off | `Settings().app_scanning_enabled is False`; `SECURESCOPE_APP_SCANNING_ENABLED` values `false` and `0` give off | `test_the_flag_is_off_by_default_and_not_set_by_any_deployment_file` passed |
| No deployment file sets it | The test also fails if `render.yaml`, `docker-compose.yml`, `wrangler.jsonc` or `backend/Dockerfile` mention it | Passed |
| Enforced by the backend, not the menu | While off, all 7 `/api/v1/app/*` routes answer 404 for a signed-in owner, an anonymous caller and a caller with a CI bearer token, for every method; nothing is written to the three tables | `test_while_off_every_route_is_404_for_everyone_and_writes_nothing` passed |
| Not bypassable by headers, query strings or path variants | `X-Organization-Id`, `X-Forwarded-For`, `X-HTTP-Method-Override`, `?enabled=true`, trailing slashes, case changes, encoded slashes | `test_the_answer_while_off_does_not_depend_on_headers_or_query_tricks` passed (an `Origin` header is refused earlier with 403 by the existing origin check; also acceptable) |
| Read from server settings only | One app with the flag on and one off in the same process answer differently, per server setting | `test_the_flag_is_read_from_the_server_settings_only` passed |
| Frontend only hides | The menu entry appears only if the server answers `/app/overview` with 200 | `appscanning.test.tsx` ("is hidden while the server has the feature off") passed |

**Operator rule:** never add `SECURESCOPE_APP_SCANNING_ENABLED` to Render, `render.yaml`, `.env` files or the Cloudflare Worker during Stage 1. An unset variable is the intended state. If it is found set to anything, stop.

### 1.4 What cannot run while dormant

| Concern | Proof |
|---|---|
| OSV or any outbound request | The default vulnerability source `UnavailableSource` raises "unavailable" and has no network code. `test_no_network_connection_is_opened_by_anything_in_app_scanning_even_when_switched_on` records every non-local socket connection during a full scan and found none. `test_app_scanning_code_imports_no_http_client_mailer_webhook_or_billing_module` fails if any App Scanning module imports an HTTP client, `socket`, `subprocess`, a mailer, webhook code or billing lifecycle code, or mentions `osv.dev`, Paddle, webhooks or notifications |
| Customer scans | Routes answer 404 (1.3). Even with the flag on in tests, a real scan ends *Failed, not counted* because the source is unavailable |
| Customer notifications | The same test asserts the number of emails sent is unchanged by a scan. No App Scanning module imports a mailer or webhook code |
| Billing | No billing, Paddle or subscription file changed (`git diff 08e46d3 --stat` lists only `plans.py` among billing files, additions only). `test_existing_plan_entitlements_are_unchanged` pins every pre-existing plan value to the values shipped at 08e46d3 |
| New entitlements | `Plan` gained `app_scans_per_month`, `app_projects`, `app_ci_tokens`. They are read only by the (404-while-off) App Scanning routes. No existing route reads them. They are provisional and not shown to customers |
| Background jobs | The hourly maintenance loop was not changed and does not touch the new tables (`grep` of `app/` for the new repository shows only the App Scanning routes, the start-up cleanup and account deletion) |
| Free users and CI tokens | Free workspaces cannot create *any* API token today (`POST /api-tokens` returns 403 because tokens require `scheduled_scans`), and no App Scanning token type exists yet. `test_a_free_workspace_cannot_get_any_api_token_and_a_paid_token_does_not_open_app_scanning` also shows that a Professional token gets 401/403 on every App Scanning route even with the flag on |

### 1.5 Existing Web Scanning and security controls unchanged

- The diff against 08e46d3 outside App Scanning files is: `alembic/env.py` (one import), `api/deps.py` (three attributes), `api/v1/__init__.py` (router registration), `billing/plans.py` (additive fields), `core/config.py` (three settings), `main.py` (start-up cleanup), `repositories/accounts.py` (account deletion also removes the new tables' rows). Review these yourself: `git diff 08e46d3 -- <file>`.
- Existing guard tests ran unchanged on the RC: authentication sweep (every route refuses a visitor unless listed public; it now runs with the flag on so the new routes are included), route coverage / cross-customer, API docs coverage, migration chain, deletion sweep, SSRF and target-verification tests (all in the full suite, section 1.6).
- **Not changed and not re-tested individually:** scanner request code, SSRF protections, authentication, sessions, CSRF. They are covered only by the full existing suite.

### 1.6 Tests and CI on the exact RC

On the final commit, run and record (the commands are those used for this audit):

```
cd backend
ruff check .                       # CI runs this
mypy app
SECURESCOPE_TEST_DATABASE_URL=<scratch PostgreSQL> pytest      # whole suite; also run once on SQLite (default) and expect the 3 known PostgreSQL-only failures (see below)
cd ../frontend
npm run lint && npm run typecheck && npm run format:check && npm test && npm run build
npx playwright test                # real backend, real browser, includes axe checks
npm audit --audit-level=high ; pip-audit -r backend/requirements.txt
python scripts/scan_secrets.py --history
```

- Then push to a **branch** (not the production branch) and confirm the GitHub `CI` workflow is green on that exact commit. Results from this session's local runs are in `docs/app-scanning-test-evidence.md` (sections 9 to 12); local runs are not a substitute for CI on the RC.
- Known environment limit: on SQLite three existing tests fail (`test_agency_queries`, two concurrency tests in `test_plans.py`) because they need PostgreSQL row locks. They fail identically without any App Scanning code. The CI runs on PostgreSQL.

---

## 2. Backup (before the deploy, every time)

1. Choose a quiet time. Free-tier Render instances sleep; wake the API first (`/api/v1/ready`) so the deploy does not coincide with a cold start.
2. Take a logical backup with the existing script (PowerShell, Docker Desktop running; the connection string is read from the environment so it is not typed or saved):
   ```
   $env:SECURESCOPE_BACKUP_URL = "<Neon connection string>"
   .\scripts\backup-db.ps1
   Remove-Item Env:SECURESCOPE_BACKUP_URL
   ```
3. Confirm the script reports the file as readable. Record the file name, size and time.
4. Prove it restores: run `.\scripts\restore-test.ps1` against a scratch database (see `docs/OPERATIONS.md` section 3 and `docs/operational-readiness-audit.md`). **A backup that has not been restored is not a backup.**
5. Note Neon's own restore window (instant restore / branch) as a second route. Create a Neon branch of production before the deploy if the plan allows; record its name.
6. Open question for the owner: the second encrypted copy of backups away from the PC is still an open item in `docs/OPERATIONS.md`. Decide whether Stage 1 waits for it.

Stop here if there is no verified backup.

## 3. Migration rehearsal and expected schema changes

### 3.1 Expected changes (this is what "success" looks like)

- `alembic_version`: `0020` becomes `0023`.
- New tables: `app_projects`, `app_scans`, `app_findings`; new indexes `ix_app_projects_organization_id`, `ix_app_scans_organization_id_created_at`, `ix_app_scans_project_id_created_at`, `uq_app_scans_organization_id_idempotency_key`, `ix_app_findings_scan_id_position`, plus the unique constraint `uq_app_projects_organization_id_name`.
- 0023: `api_tokens` gains `scope` (default `web`) and `expires_at`; `app_scans` gains `token_id`, one foreign key and one index. No other table, column, index or constraint changes. All three new tables hold zero rows; every existing token reads `scope = 'web'`.

### 3.2 Rehearse on a non-production database that resembles production

1. Create a scratch Neon branch or a local PostgreSQL database from the backup restored in section 2.4.
2. Point the RC at it and migrate: `SECURESCOPE_DATABASE_URL=<scratch> python -m app.database.migrate`. Record the time taken.
3. Verify the schema (queries to run on the scratch database):
   ```
   select version_num from alembic_version;                              -- expect 0023
   select tablename from pg_tables where tablename like 'app\_%' order by 1;  -- expect the three tables
   select (select count(*) from app_projects) + (select count(*) from app_scans) + (select count(*) from app_findings);  -- expect 0
   ```
4. Start the RC against the scratch database (flag unset) and run the smoke tests of section 5.
5. Rehearse the rollback of section 8 on the same scratch database. Record results.

Local rehearsals already done (26 Oct 2026, local PostgreSQL 16 and SQLite, **empty** databases, not production data): upgrade 0020 to 0023, downgrade to 0020, upgrade again; schema snapshot equal after the round trip. Not done: a rehearsal on a restored copy of the real production data.

## 4. Deployment

Only after sections 1 to 3 are signed off **and** the owner gives a separate deployment approval. The owner pushes; this runbook does not push.

1. Confirm `SECURESCOPE_APP_SCANNING_ENABLED` is **not** set in Render (Environment tab) and not in the Cloudflare Worker.
2. Record: RELEASE ID (commit), time, backup file name, Neon branch name.
3. Push the RC (owner, from PowerShell, after saying "let deploy it"). CI runs; Cloudflare rebuilds the frontend; Render redeploys the API and runs the migration at container start.
4. Watch the Render deploy log. Expected: migration lines `Running upgrade 0020 -> 0021`, `0021 -> 0022` and `0022 -> 0023`, then `Application startup complete`. If the log shows a migration error, go to section 8 immediately.
5. Do **not** set the flag, add pricing, change billing, or send any announcement.
6. Record the migration status (`alembic_version` = 0023 if you can read it, otherwise the log lines) and the time the new version became healthy.

## 5. Smoke tests (run immediately after deployment)

| # | Check | Expected | Result / time |
|---|---|---|---|
| S1 | `GET /api/v1/ready` | 200 | |
| S2 | Open the site, sign in with a test account | Works; dashboard loads | |
| S3 | Web Scanning: scan a verified domain you own, open the result, export once | Scan completes; findings show; export works | |
| S4 | Targets: unverified domain is still refused; private address `http://127.0.0.1` still rejected | As before | |
| S5 | Open the menu | **No "App Scanning" entry** | |
| S6 | `GET /api/v1/app/overview` while signed in (browser address bar or curl with your session) | **404** | |
| S7 | `POST /api/v1/app/scans` with any body | **404** (not 401/403/422, not 201) | |
| S8 | Same two calls anonymously, and with a CI token | **404** | |
| S9 | Free test account: create an API token | 403 (as before) | |
| S10 | Cross-customer check with two test accounts (existing guard) | Second account cannot see the first account's targets or scans | |
| S11 | Account deletion on a throwaway account | Works | |
| S12 | Platform Health page (operator) | Database reachable; no new errors | |
| S13 | Render logs for 15 minutes | No `app scan` lines other than possibly a start-up warning `could not clean up unfinished app scans at start-up` (which would mean the table is missing: investigate); no outbound-request errors; no mail sent that you did not trigger | |
| S14 | Neon dashboard / query: the three `app_*` tables | Exist, zero rows | |

Any failure of S1 to S4, S9 to S11 or any 2xx/4xx other than 404 on S6 to S8 triggers rollback consideration (section 7).

## 6. Monitoring after deployment

- Uptime monitor on `/api/v1/ready` (see `docs/OPERATIONS.md` section 1).
- Check Render logs again after 1 hour and after 24 hours.
- Confirm the weekly backup task still runs.

## 7. Rollback triggers

Roll back if any of these occurs: the API does not become healthy within 10 minutes; the migration fails or is partial; S1 to S4 or S9 to S11 fail; any App Scanning route returns anything but 404; any App Scanning data appears; unexpected outbound requests or mail; an error rate clearly above normal. **Who decides:** the owner. The engineer on duty may pause and escalate, but does not run a database rollback without the owner's explicit approval.

## 8. Rollback procedure

**Never reverse a migration by hand on production and never "just redeploy the old image": it will not start (fact 2).** Choose by what broke.

### 8.1 Path A (default): restore from the pre-release backup, then deploy the previous code

Use when the migration failed halfway, data looks wrong, or you are unsure.

1. Stop and announce: the owner authorises.
2. Restore the section 2 backup (or the Neon branch / instant restore) into a **new** database; do not overwrite the damaged one. Follow `docs/OPERATIONS.md` section 3. Note: this loses any data written since the backup (accounts, scans). Estimate that loss before deciding.
3. Point Render's `SECURESCOPE_DATABASE_URL` at the restored database.
4. Redeploy the previous code (`git revert` the release, or Render's "redeploy earlier build"). The old image's migration step then finds `alembic_version` 0020 and starts.
5. Verify with the smoke tests S1 to S4, S9 to S11.

### 8.2 Path B (only if the three tables are empty): downgrade with the new image, then deploy the previous code

Rehearsed on a scratch database only (26 Oct 2026, empty tables). Valid only while the feature has never been enabled.

1. The owner authorises.
2. **Check first:** `select count(*) ...` on each of `app_projects`, `app_scans`, `app_findings` must all be 0. If any is above 0, use Path A (the downgrade would delete that data).
3. Take a fresh backup (section 2) even though only empty tables are removed.
4. Using the *release candidate's* code (it contains 0021, 0022 and 0023): `alembic downgrade 0020` against production (`SECURESCOPE_DATABASE_URL=<production> python -c "from alembic import command; from app.database.migrate import alembic_config; ..."` or the equivalent `alembic -c` call). This removes `app`-scope tokens (none exist while the feature has been off; check `select count(*) from api_tokens where scope <> 'web'` is 0 first), drops the two added columns on `app_scans` and `api_tokens`, and drops exactly the three tables.
5. Confirm `alembic_version` = 0020 and the tables are gone.
6. Redeploy the previous code.
7. Verify with smoke tests.

### 8.3 Application-only problem (database fine)

If the migration succeeded and only the application misbehaves, the database is at 0023 and the old image cannot start on it. Fix forward (a new commit that turns the problem off, for example reverting only the code that misbehaves while keeping the migration files in the tree), or use Path A or B. Do not deploy an image that lacks revision 0023.

### 8.4 After any rollback

Rescan a verified site, check Platform Health, record what happened, and write the incident down (use `docs/INCIDENT_TEMPLATE.md`).

### 8.5 What was and was not proven about rollback

- **Proven (local, scratch, empty):** the previous release's own test suite and a targeted script run on a database at 0023 with the previous code (sections 12 and 14 of the test evidence: 1099 passed); the previous container cannot run its start command on 0023; Path B returns the schema to 0020 and the previous code then starts and answers `/ready` with 200.
- **Not proven:** Path A and B on a copy of the real production data and size; timing; Neon-specific behaviour (branching, instant restore); behaviour on the Render free instance.

---

## 9. Items that stay open and block later stages (not Stage 1)

| Item | State | Needed before |
|---|---|---|
| OSV terms, API docs, rate limits, data licence, caching and redistribution rules (V1 to V7 in `app-scanning-v1-privacy-and-licensing.md`) | **BLOCKED.** The official OSV documentation could not be fetched from the build environment; nothing about OSV is verified. Evidence has to be collected from the official pages with a date, by the owner or by a session with access; no conclusion is to be written without it | Enabling any lookup |
| Component licence register (vulnerability database, secret scanner, SAST engine and rules, Action image, any new dependency) | Every row "not reviewed". **BLOCKED FOR RELEASE** | Bundling or shipping any component |
| Privacy notice | Provisional draft only (section 4a of the privacy file). **Publication blocked** until the actual data flow and the OSV terms are verified; the draft must be changed if the implementation differs | Enabling the flag |
| Plan allowances 5 / 100 / 500 runs per month, and 1 / 10 / 50 projects | Provisional product hypotheses, not commercial entitlements, not shown to customers, billing untouched | Making them binding |
| Plan-limit validation | Not done: representative workloads, measured time/memory/storage/cost on the real instance, behaviour of server-side enforcement under load on the 0.1 CPU instance, compatibility with the subscription model | Making limits binding |
| Counting rule | Implemented and tested (accepted request for one project = one run; invalid and unsupported requests, failed and interrupted runs and duplicate retries are not counted). Needs owner confirmation that infrastructure failures never consume a run in every path | Making limits binding |
| Per-project hourly limit | Implemented server-side (database counted); value (6) provisional | Making limits binding |
| Separate counter | Implemented: usage is computed from `app_scans`, separate from web `scans` | |
| CI tokens for App Scanning | No token type exists; Free cannot create any token | CI phase |
| End-to-end and accessibility tests on the RC | Run locally on the page (section 11 of the test evidence); must be run again on the RC and green in CI | Stage 1 sign-off |
| Rollback on real data | Not rehearsed on production-sized data | Stage 1 sign-off (recommended) |
| Second encrypted backup copy | Open owner item in `docs/OPERATIONS.md` | Owner decision |

## 10. Enabling the feature is a separate decision

Nothing in this runbook turns it on. Before the flag may be set anywhere, the owner records a separate written approval that closes: OSV verification (V1 to V7) and the privacy notice (G1 and G3), the licence register (G2), the plan limits question, a load result on the real instance, and a fresh run of sections 1.6 and 5 with the flag on in a non-production environment. Then: staging first, then the owner's own workspace only.

## 11. Evidence and sign-off

Fill this in during execution. An empty row means not done.

| Step | Command or action | Result | Time (UTC) | By |
|---|---|---|---|---|
| RELEASE ID (commit) | | | | |
| `git status` clean | | | | |
| CI green on RC (link) | | | | |
| Full backend suite on PostgreSQL | | | | |
| Frontend suite and build | | | | |
| Playwright / axe | | | | |
| Backup file name and size | | | | |
| Restore test of that backup | | | | |
| Migration rehearsal on restored copy (time, schema queries) | | | | |
| Flag not set in Render / Worker | | | | |
| Owner deployment approval | | | | |
| Deploy: migration log lines | | | | |
| Smoke tests S1 to S14 | | | | |
| 1-hour and 24-hour log check | | | | |
| Outstanding issues recorded | | | | |

Sign-off (all required): engineer __________ owner __________ date __________

Explicit approval required before enabling the feature: **not given.**

## Pilot allow-list (before the flag is ever switched on in production)

`SECURESCOPE_APP_SCANNING_ALLOWED_ORGS` is a JSON list of workspace ids, for example `["<id>"]`. While the feature is on, only listed workspaces can use it; every other workspace gets the `404` of a feature that is off. `[]` means nobody. The app refuses to start with the feature on, an https address and no list, so forgetting the list cannot open the feature to everyone. It adds a gate on top of the plans and changes no plan value, billing or Web Scanning behaviour. A workspace id is `organizations[0].id` in `GET /api/v1/auth/me` for that account.

Order for a pilot: set the list first (and `SECURESCOPE_APP_SCANNING_ENABLED` second, in the same Render save), then check that a workspace that is not listed gets `404` on `/api/v1/app/overview`. Switching the flag off again is the kill switch.
