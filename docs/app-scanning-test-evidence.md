# App Scanning: test evidence

Date: 26 Oct 2026. **Only Step B (the redaction module and canary harness) exists. Nothing else in App Scanning is built or tested.** This file exists so that claim is explicit, and so later phases append real results here rather than rewriting history.

## 1. What has been verified so far

| Item                                                                                               | How                                                                                         | Result                                                       |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Existing web scanning, permissions, plans, CI, reporting and logging behave as the audit describes | Read the source files named in `app-scanning-audit.md`                                      | Read only; nothing was executed for this audit               |
| No application code, migration, dependency or configuration was changed by Phase Zero              | `git status` shows only new files under `docs/`                                             | See the batch commit                                         |
| Existing test suite state                                                                          | Last full runs were for batches 27 to 29 (see `load-test-results.md`, `dark-mode-audit.md`) | Not re-run for this docs-only batch, because no code changed |

## 2. What is not verified

- OSV response format: the field names for severity, affected ranges and fixed versions come from documentation reading and must be checked against real responses at the start of Phase 2.
- OSV rate limits and availability behaviour under load.
- Licence terms of any rule set or database.
- Any claim about performance of parsing on the 0.1 CPU instance.
- Everything in `app-scanning-security-model.md` section 2 is a requirement, not a result.

## 3. Test plan to be filled in

| Phase | Test group                                                                | Status              |
| ----- | ------------------------------------------------------------------------- | ------------------- |
| 2     | Manifest parsing (valid, malformed, oversized, nested, unsupported)       | Not written         |
| 2     | Vulnerability result normalisation, including `unavailable` → incomplete  | Not written         |
| 2     | Redaction and canary secret across DB, API, PDF, webhooks, emails, logs   | Not written         |
| 2     | Cross-customer, role and plan-limit tests                                 | Not written         |
| 2     | No execution of project scripts (patched subprocess, read-only directory) | Not written         |
| 2     | Outbound payload and destination                                          | Not written         |
| 2     | Web Scanning regression (existing suite)                                  | Existing; to re-run |
| 3     | CI schema fuzz, injection and escaping                                    | Not written         |
| 4     | Report consistency, golden test of existing web report                    | Not written         |
| 5     | Exit codes, token scope                                                   | Not written         |
| 7     | Load and abuse on the real instance size                                  | Not run             |

## 4. Results log

| Date        | Phase         | Command         | Result       |
| ----------- | ------------- | --------------- | ------------ |
| 26 Oct 2026 | 1 (docs only) | none applicable | No tests run |

Rule: an entry is added only with the command that was run and its actual output summary. A phase is not described as tested until its rows above are written and passing.

## 5. Step B results (26 Oct 2026, batch 32)

| Command                                                               | Result                                                                                                                                                                                                                                                                                                |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pytest app/tests/test_appscan_redaction.py`                          | 43 passed                                                                                                                                                                                                                                                                                             |
| Full backend suite on PostgreSQL 16 (`SECURESCOPE_TEST_DATABASE_URL`) | 1142 tests, 0 failed, 0 skipped                                                                                                                                                                                                                                                                       |
| Same suite on SQLite (the default)                                    | 3 failures in existing tests: `test_agency_queries` (statement row count) and two concurrency tests in `test_plans.py`. They fail identically with the new files removed, and the repository's CI runs on PostgreSQL, where they pass. An environment limit, not caused by this batch, not fixed here |
| `ruff check app`                                                      | All checks passed                                                                                                                                                                                                                                                                                     |
| `mypy app`                                                            | Success, 192 source files                                                                                                                                                                                                                                                                             |
| `ruff format --check` on the new files                                | Clean (23 older files in `app/` would be reformatted; untouched)                                                                                                                                                                                                                                      |
| Repository secret scan                                                | No secrets found                                                                                                                                                                                                                                                                                      |

Defects found by the tests and fixed in this batch: the credential-assignment pattern was quadratic (about 1.4 s on 5,000 dotted characters) and is now a bounded keyword look-ahead; the pathological-input test is the permanent guard. Mutation checks, each caught by a test: a mask that keeps the last four characters, a rejection message that adds content, and oversized text treated as clean.

Not tested because it does not exist yet: run accounting, duplicate-request handling, plan isolation, browser-upload restriction for Free, server-side enforcement, any route, table or token rule (Steps C and H).

Known blind spots of the redaction rules (documented in the module): secrets split across lines, low-entropy passwords with no keyword nearby, and pure hexadecimal strings of 32, 40 or 64 characters.

## 6. Step C1 results (26 Oct 2026, batch 33): tables, counter and run accounting

Covers the repository, plan catalogue and migration only. **There are no routes, no parsers and no UI**, so nothing here shows route-level enforcement, upload handling or the Free-plan token restriction at an endpoint (those are Step H).

| Check                                         | Result                                                                                                                                                                                                |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_appscan_accounting.py` on PostgreSQL 16 | 30 passed                                                                                                                                                                                             |
| Same file on SQLite                           | 28 passed, 2 skipped (the two thread-race tests need PostgreSQL row locks, like the existing plan concurrency tests)                                                                                  |
| Mutation checks (each caught by a test)       | failures counted as runs; failed runs counted in usage; idempotent replay removed; workspace filter removed from `get_run`, `start_run` and `finish_run`; hourly limit disabled; Free given CI tokens |
| Full backend suite on PostgreSQL              | see the batch 33 summary                                                                                                                                                                              |
| `ruff`, `mypy`                                | clean                                                                                                                                                                                                 |

## 7. Step C2 results (26 Oct 2026, batch 34): manifest parsers

`backend/app/appscan/manifests.py` reads `package-lock.json` (v1, v2, v3), `package.json` (exact versions only) and `requirements.txt` (`==` pins only). It is imported by nothing else yet: no route, no lookup, no UI.

| Check                                                       | Result                                                                                                                 |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `test_appscan_manifests.py`                                 | 37 passed                                                                                                              |
| All three App Scanning test files together on PostgreSQL    | 110 passed                                                                                                             |
| Mutation checks (each caught by a test)                     | JSON depth check removed; ranges accepted in `package.json`; binary and archive detection removed; package cap removed |
| `ruff check`, `ruff format --check` (new files), `mypy app` | clean                                                                                                                  |
| Full backend suite                                          | **not re-run for this batch** (only new, unreferenced files were added; the last full run was 1172 passed on batch 33) |

What the tests prove: valid files parse; ranges, URLs, local paths, options and unpinned lines are reported as unsupported with fixed reasons and never copied; hostile input (empty, binary, archives, bad UTF-8, malformed JSON, deep nesting, oversized, 20 000-package cap, long and pathological lines) ends in a clean fixed-text error and is fast; a 15 000-package lockfile parses in under 5 seconds on this machine (the 0.1 CPU instance is not measured); no process is started, no network is opened and no file is written while parsing; no file content other than package coordinates appears in a result.

Not proven: behaviour on the real instance size, and that these formats are what customers will upload.

## 8. Step C3 results (26 Oct 2026, batch 35): findings storage and the dependency scan pipeline

New: `app_findings` table (migration `0022`, additive), `appscan/vulns.py` (the interface a vulnerability source must meet), `appscan/pipeline.py` (statuses, normalisation, sanitising), and `store_result` / `get_findings` in the repository. **No network client exists and nothing is wired to a route.** Every lookup in the tests is a fake.

| Check                                   | Result                                                                                                                                         |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_appscan_pipeline.py`              | 33 passed                                                                                                                                      |
| Full backend suite on PostgreSQL 16     | 1242 tests, 0 failed, 0 skipped                                                                                                                |
| Mutation checks (each caught by a test) | source outage read as clean; unsupported entries ignored; reply-length check removed; advisory text not cleaned; reference links not validated |
| `ruff check app`, `mypy app`            | clean                                                                                                                                          |

Proven with fakes: outage, crash, partial answers, misaligned replies and time budget all produce Incomplete or Failed and never a clean result; findings never make a run unsuccessful; a failed run is stored but not counted; a final run's result is not overwritten; another workspace sees no findings; hostile advisory text is cleaned; a canary secret in advisory text never reaches the database.

Not proven: the shape of real OSV responses (field names, severity and fixed-version encoding), real latency and size, and behaviour on the real instance.

## 9. Step C4 results (26 Oct 2026, batch 36): API routes behind a disabled feature flag

New: `api/v1/app_scans.py` (7 routes under `/api/v1/app`), `schemas/app_scan.py`, `UnavailableSource` (the default source), `list_runs` in the repository, start-up interruption of unfinished app runs. **The flag `APP_SCANNING_ENABLED` is off by default and every route answers 404 until it is on. No real vulnerability source exists, so a real scan ends Failed (not counted).** No frontend yet.

| Check                                                         | Result                                                                                       |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `test_appscan_routes.py` + route-coverage + API-docs guards   | see the batch 36 summary for the final count                                                 |
| Mutation checks (each caught by a test)                       | feature flag check removed; viewer allowed to create; streamed size cap removed; pipeline defect read as clean; idempotent replay recharged; id validation removed |
| `ruff check app`, `mypy app`                                  | clean                                                                                        |

Proven: flag off gives 404 for every route including signed-out callers; each role gets exactly what the permission matrix allows; another workspace gets 404 on every id route; malformed ids are 404; bad files, duplicates, oversized bodies (declared and chunked) are refused and not counted; plan project cap 403, monthly cap 403, hourly cap 429; idempotent retries are not charged twice and a key cannot be reused across projects; outages and pipeline defects end Incomplete or Failed, never "no findings"; no score or grade in any response; canary secrets are not echoed or stored; audit events carry ids only; runs left unfinished at start-up become interrupted and uncounted.

Defect found by the tests: re-entering the application lifespan (a second `TestClient` context) interrupts queued runs, which is the intended restart behaviour; one older accounting test relied on the opposite and was corrected.

Not proven: real source behaviour (OSV is blocked), behaviour under the 0.1 CPU instance, the concurrency semaphore under real parallel load, and any browser UI.

## 10. Step D1 results (26 Oct 2026, batch 37): browser page

New: one "App Scanning" page (`pages/AppScanning.tsx`), API client functions, a hook that shows the menu entry only when the server answers `/app/overview` (the feature is off by default, so the entry is hidden). The navigation itself is unchanged; its redesign remains a separate batch.

| Check | Result |
| --- | --- |
| `appscanning.test.tsx` | 11 passed |
| Full frontend unit suite | 258 passed, 0 failed (31 files) |
| `eslint`, `tsc -b`, `prettier --check`, `npm run build` | clean |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Mutation checks (each caught) | non-https links allowed; browser size check removed; role gate removed |

Defect found by the existing suite: the menu check fired for unverified accounts, which must request nothing; it now waits for a verified email.

Proven: usage and limitations shown before any scan; a clean result never says "secure" and shows no score or grade; an incomplete result is styled as a problem and lists what was not checked; hostile advisory text renders as text and `javascript:` links are dropped; server refusals are shown and the form stays usable; oversized files are refused before upload; roles that cannot create see no forms; the menu entry is hidden when the server returns 404.

**Not run:** Playwright end-to-end and axe accessibility tests for this page (they need the running backend and browser; no such run was made), mobile and dark-mode visual checks, keyboard-only walkthrough. These are required before the feature is switched on.

## 11. Step D2 results (26 Oct 2026, batch 38): real-browser tests

`e2e/appscanning.e2e.ts` (5 tests) runs against the real backend with `APP_SCANNING_ENABLED` on (set in the e2e server only). Chromium 1194 (Playwright), Linux.

| Check | Result |
| --- | --- |
| `appscanning.e2e.ts` | 5 passed: add project and upload; honest "Scanner error, not counted" result (the e2e backend has no vulnerability source); malformed file refused and uncounted; axe WCAG 2 A/AA, no serious or critical violations in dark and light, before and after adding a project; 375 px wide with no horizontal scroll and keyboard entry |
| Whole e2e suite (116 tests) | first run 111 passed, 3 failed: one was my test matching two elements (fixed); two in `targets.e2e.ts` failed at registration ("Confirm your email address" heading not found) |
| Re-run of `targets.e2e.ts` with the new file | both passed (7 of 7 passed together) |

The two `targets` failures did not reproduce. The cause is **not established**; the likely candidate is a limit on repeated registrations late in a long run on one address, but that was not checked. The whole suite was not re-run end to end after the fix.

Still not done: a manual screen-reader pass, and a visual check of the findings table with many rows.

## 12. Stage 1 preparation results (26 Oct 2026): dormant deployment checks

Everything below ran on this repository and on scratch databases (local PostgreSQL 16, SQLite). **Nothing was run against production, and no production data, configuration or flag was touched.** See `app-scanning-stage-1-runbook.md`.

| Check | Result |
| --- | --- |
| `test_appscan_stage1.py` (12 tests) | 12 passed on PostgreSQL, 12 passed on SQLite |
| Mutation checks on those tests | 7 of 7 caught: flag default on; route guard removed; HTTP client imported into App Scanning code; migration altering an existing table; `render.yaml` setting the flag; Free given CI tokens; a changed Free allowance |
| Full backend suite, current code, PostgreSQL | **1282 passed, 0 failed** |
| `ruff check`, `mypy app` | clean (205 files) |
| **Previous release (08e46d3) full suite on a database migrated to 0022** (old code, the two new revision files copied in) | **1099 passed, 0 failed** |
| Previous release code, scripted: register, read scans/targets/overview/ready, delete an account that owns App Scanning rows | all 200; deletion 204; app rows cascade to zero |
| Previous release container start command on a database at 0022 **without** the new revision files | **fails**: `Can't locate revision identified by '0022'`. A code-only rollback does not work |
| Downgrade 0022 to 0020 with the new code on an empty scratch database, then previous release migrate and start | tables dropped, `alembic_version` 0020, previous release migrate exit 0, `/api/v1/ready` 200 |
| Schema snapshot (columns, indexes, foreign keys, unique constraints of every existing table) before and after upgrade, and after downgrade | identical |

Defect found and fixed: the start-up cleanup of unfinished App Scanning runs could have stopped the whole application from starting if the new tables were missing; it is now non-fatal (logged warning).

Test-design note: a first version of the header-bypass test expected 404 where an existing origin check answers 403 earlier; both are refusals and the test accepts either for that one header.

Not proven: the migration on a restored copy of production-sized data (lock time, duration); Neon-specific behaviour; Path A (restore) and Path B (downgrade) on production; the Render free instance. The pre-deployment CI run on the final commit has not happened (the Stage 1 additions are uncommitted at the owner's instruction). The frontend and Playwright suites were not re-run in this step because no frontend file changed since section 11.

## 13. Step E1 results (26 Oct 2026): CI submission module (not wired to any route)

New: `appscan/submission.py` (strict schema, secret refusal, normalisation of static-analysis and secret-detection results), `CodeFinding` in the pipeline, repository support for code findings (path and line, no package fields). **No route accepts a submission yet** and no token type for App Scanning exists; wiring needs an owner-reviewed token design (scope field and migration on the token table, Free denied).

| Check | Result |
| --- | --- |
| `test_appscan_submission.py` | 44 passed |
| With the pipeline tests | 77 passed |
| Full backend suite on PostgreSQL | **1326 passed, 0 failed** |
| `ruff check`, `mypy app` | clean |
| Mutation checks (each caught) | secret check removed; secret finding keeps submitter text; skipped check still "complete"; `..` in paths allowed; unknown fields allowed; findings for a check that did not run trusted; stored evidence not redacted; fingerprint depends on more than rule, path and occurrence |

Proven: unknown fields, bad types, traversal and absolute paths, control characters, oversized lists and deep nesting are refused with fixed text that never repeats the input; a secret in any field, key or value refuses the whole submission before anything is read, with no echo; secret findings never keep the submitter's title or message; a skipped or missing check gives Incomplete; every scanner is labelled as reported by the submitter; hostile text is kept as text (escaping is a render-time duty, covered for the page by earlier tests); 5,000 findings parse in under 10 seconds here.

Not proven: any route, token scope or rate limit for submissions; rendering of these findings in the page and in PDF reports (the page's table is built for dependency findings); real tool output (Semgrep, Gitleaks) converted to this schema; behaviour on the real instance.

## 14. Step E2 results (26 Oct 2026): CI token scopes and authenticated submission route

New: migration `0023` (`api_tokens.scope`, `api_tokens.expires_at`, `app_scans.token_id`), token scope enforced in `bearer_actor` (`/ci/*` accepts `web` tokens only; `/app/ci/submissions` accepts `app` tokens only), `app` token creation gated by the server-side plan flag `app_ci_tokens` and the feature flag, `POST /api/v1/app/ci/submissions`, a database-counted per-token hourly limit, and `AppScanRepository.accept_run` shared by browser uploads and CI submissions. The feature flag stays off by default; nothing was deployed or enabled.

| Check | Result |
| --- | --- |
| `test_appscan_ci_tokens.py` (new; 16 required areas, one negative test per boundary) | 36 passed (PostgreSQL), also passes on SQLite |
| Migration 0023 test (existing token reads back `web`, no expiry; only `api_tokens` and `app_scans` change; downgrade restores 0022 exactly and removes `app` tokens only) | passed, with the 0021/0022 additive test scoped to those revisions |
| Existing token, GitHub Action, integration and App Scanning suites | passed (included in the full run) |
| **Full backend suite on PostgreSQL** (`pytest -p no:cacheprovider`) | **1363 passed, 0 failed.** The first full run used `-p no:logging`, which removed `caplog` and gave 7 fixture errors in three files (`test_domain_verification`, `test_log_secrets`, `test_mailer`); those 24 tests pass when run normally, so 1356 + 7 = 1363 |
| `ruff check app alembic`, `mypy app` | clean (208 files) |
| Mutation checks (each caught by `test_appscan_ci_tokens.py` and `test_integrations.py`) | scope check removed; plan not rechecked at use; plan not checked at creation; flag guard removed on the router; flag not checked at token creation; expiry ignored; revocation ignored; token scope forced to `app`; project lookup not scoped to the workspace; archived projects accepted; idempotency key not used; per-token limit disabled; secret refusal removed; size cap removed; owner role not rechecked; web CI route accepting `app` scope. 17 of 17 caught (a first workspace mutation was a no-op and was redone against the real project query) |
| **Previous release (08e46d3) full suite on a database migrated to 0023** (old code, revision files 0021 to 0023 copied in) | **1099 passed, 0 failed** (1092 plus the same 7 `caplog` tests re-run without the flag) |
| Previous release, scripted: register, read scans/targets/overview/ready, delete an account that has App rows | all 200, deletion 204, App rows cascade to zero |
| `scripts/scan_secrets.py --history` | no secrets found in files or history |
| `pip-audit -r backend/requirements.txt` | no known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Frontend | no frontend files changed; frontend unit tests not re-run |
| Playwright e2e (full run) | 112 passed, 2 failed (`targets.e2e.ts`: two registration tests). The same two pass when `targets`, `appscanning` and `integrations` are run alone (10 passed). The same pattern was seen in an earlier full run; the cause is **not established** |

Not proven: rate limiting under real multi-process load (tested with two app instances sharing one database in one test process); the token-creation screen (not built, so `app` tokens can only be created through the API); real tool output from Semgrep or Gitleaks; migration 0023 on production-sized data; lock time on `api_tokens` in production.

## 15. Step E2b results (26 Oct 2026): pilot settings, flaky e2e root cause, independent review

**Provisional pilot settings** (owner decision, not commercial policy): 30 submissions per token per hour (`APP_CI_SUBMISSIONS_PER_TOKEN_PER_HOUR`) and 90-day App token lifetime (`APP_CI_TOKEN_DAYS`, was 365). Both are application settings, enforced in the server, the hourly count in the database. A test asserts the defaults and that a changed lifetime is honoured; Web tokens still have no expiry.

**Root cause of the two `targets.e2e.ts` failures (established with evidence).** The failure page showed the alert "Too many sign-ups from your address". The end-to-end server runs with the production sign-up limit of 10 per address per hour, kept in that server's memory. After a failing full run the test database held exactly 10 users; the suite registers 13 accounts, so registrations 11 to 13 (the two `targets` tests, which run late, and one more) were refused. The tests passed alone because a fresh server had a fresh counter. It was not a race, shared state or ordering fault. Fix: `SECURESCOPE_REGISTRATIONS_PER_IP_PER_HOUR=1000` in `frontend/playwright.config.ts`, for the test server only. No assertion was weakened, no sleep added, nothing skipped, production limit unchanged. After the fix the full run registered 13 users and passed.

**Independent security review** (a separate reviewer that had not written the code; report summarised, nothing verified only by the reviewer was left unfixed):

| Finding | Class | Action |
| --- | --- | --- |
| V1: JSON parsing and the secret check ran on the event loop; a 3.5 MB document of many short strings took about 5.5 s to refuse, stalling the instance | Verified defect (medium) | Parsing now runs in a worker thread under the one-at-a-time App Scanning semaphore. Test: parsing has no running event loop. Mutation caught |
| T1: code from before token scopes would accept an App token as a Web token (and ignore expiry) after a rollback without a downgrade | Theoretical, plausible | App tokens now start with `ssa_`; older code accepts only `ssk_`. Tests and mutation. Runbook updated |
| T2: a browser upload could use the key `ci:K` and meet a CI key | Theoretical (same workspace, no cost) | `ci:` keys are refused on `/app/scans` with 422. Test and mutation |
| T3: no read timeout on the request body | Theoretical | 30-second limit, 408. Test and mutation. A token revoked while its upload is in flight is still honoured for that request (authenticated before the body); accepted, not changed |
| T4: strings over 20,000 characters are reported as "contains a secret" | Theoretical, safe | Not changed; wording is misleading but safe |
| T5: Web and App tokens share the five token slots per workspace | Design note | Not changed |
| T6: an unexpected error after a run is accepted left it queued | Theoretical | Now ends Failed (not counted) and re-raises. Test and mutation |

Reviewer's "checked and sound" list (scope isolation: the only caller of token authentication is the shared bearer function; flag checked before authentication; plan checked at creation and on every use; expiry, revocation and owner role checked per request; project lookup scoped to the token's workspace; replay cannot double-count; database lock serialises accounting; fixed error text with no input echo; migration upgrade additive and downgrade deleting rather than converting App tokens) matches the tests in `test_appscan_ci_tokens.py`. The reviewer did not run the full suite and did not review `test_appscan_submission.py` in depth.

Not fixed on purpose: the 4 MiB document cap stays (5,000 findings need it); rejected documents are not counted against the per-token database limit (only the in-memory 1,000-per-hour token limiter and the one-at-a-time semaphore bound them).

**Final results after the last change:**

| Check | Result |
| --- | --- |
| Full backend suite on PostgreSQL | **1369 passed, 0 failed** |
| New token file on SQLite, with the migration tests | 55 passed |
| `ruff check app alembic`, `mypy app` | clean (208 files) |
| Mutation checks | 22 of 22 caught (17 earlier plus parsing on the loop, shared prefix, open `ci:` namespace, body timeout, failed-after-accept handler) |
| Frontend: `eslint`, `tsc`, `vitest` | clean, 258 passed (no frontend source changed; only `playwright.config.ts`) |
| Playwright e2e, full run | **114 passed, 0 failed** |
| `scan_secrets.py --history`, `pip-audit`, `npm audit --omit=dev` | no secrets, no known vulnerabilities, 0 vulnerabilities |
| Previous release (08e46d3) on the 0023 schema | 1099 passed and the scripted check passed, run before this step. The migration did not change in this step, so it was not re-run; the `ssa_` prefix change only makes older code stricter |

Not proven: behaviour under real multi-process load; migration 0023 on production-sized data; real Semgrep or Gitleaks output. App Scanning remains off by default and nothing was committed, pushed or deployed.

## 16. Final pre-commit review (26 Oct 2026): resource protection, revocation in flight, token slots

Measured before changing anything: parsing the largest legal submission (5,000 findings, 0.97 MB) took 0.59 s; refusing hostile documents took 0.5 to 3 s. In a worker thread the event loop stalled for at most 14 ms while that ran (a ticker task measured the gaps).

| Point | Finding | Fix | Evidence |
| --- | --- | --- | --- |
| 1. Input size | Body capped at 4 MiB while streaming (declared and chunked). The secret check cost time per string, so a small document of 580,000 short strings took about 3 s to refuse | A document with more than 100,000 values is refused (`too_large`) before the secret scan. A full legal submission is about 85,000 | `test_a_document_with_too_many_values...`, `test_the_largest_legal_submission_is_still_accepted` |
| 1. Concurrency | The slot was freed when the request ended, but a thread cannot be stopped: a cancelled request freed the slot while its thread was still running, so more than one heavy check could run at once. Waiting for a slot was unbounded | `_run_exclusive` frees the slot only when the thread has finished; waiting is limited to 10 s (`503`, `Retry-After`) | `test_the_processing_slot_is_only_freed_when_the_thread_has_really_finished`, `test_a_request_waits_a_bounded_time...` |
| 1. Timeout | No limit on checking time | 20 s limit, refused as `too_complex`, nothing stored, slot still held until the thread ends. Body read limited to 30 s (`408`) | `test_a_check_that_takes_too_long...`, `test_a_slow_body_is_cut_off` |
| 1. Event loop | Parsing already ran off the loop | Unchanged, now also tested under a CPU-heavy document | `test_the_event_loop_keeps_running...` (limit 0.25 s; measured about 0.015 s) |
| 2. Revocation | The token was checked at the start of the request only. A token revoked or expired during upload or while waiting for a slot would still start a run | The token is checked again inside the database transaction that records the run, under the workspace lock. Refused with `401`, nothing stored, nothing counted. A replay with a revoked token is refused as well. A run already accepted completes (documented) | `test_a_token_revoked_while_its_request_is_in_flight...`, `...expires while...`, `test_a_retry_after_revocation_is_refused_not_replayed`; each request authenticates anew, so queued or retried requests cannot skip the checks |
| 3. Token slots | The limit of five tokens was one count for the workspace. An App token would have taken a slot that a Web Scanning integration needs, so a workspace with four Web tokens and one App token could not make a fifth Web token | The limit is counted per scope (5 Web, 5 App). Existing Web behaviour is unchanged: all existing tokens are Web | `test_app_tokens_never_use_up_the_slots_of_web_integrations`; `test_integrations.py` passes unchanged. Compatibility note in `docs/API.md`: a workspace can now hold up to 10 tokens in total |

Mutation checks added (each caught): node cap removed; slot released on cancellation; unbounded wait; no processing timeout; processing back on the loop; token not re-checked at accept; revocation ignored at accept; expiry ignored at accept; token limit counting both scopes. (A first "slot never released" mutant only showed up as a hung suite; it was replaced by a proper early-release mutant and caught by assertion. One mutation run was killed by a timeout and left a mutated line; it was restored and the files were checked for mutation markers.)

Rerun after the last code change:

| Check | Result |
| --- | --- |
| Full backend suite, PostgreSQL | **1379 passed, 0 failed** |
| Token, Stage 1 and submission tests, SQLite | 109 passed |
| `ruff check app alembic`, `mypy app` | clean (208 files) |
| Playwright e2e, full run | **114 passed, 0 failed** |
| `scan_secrets.py --history`, `pip-audit` | no secrets; no known vulnerabilities |
| Frontend unit tests, `npm audit` | not rerun: no frontend source changed since they passed (258 passed, 0 vulnerabilities); only `playwright.config.ts` changed earlier |
| Previous release on the 0023 schema | not rerun: migration 0023 did not change in this review |

Remaining risks: instance-level limits are per instance (one check at a time per instance, so many requests queue to 503 under load); a hostile document can still use up to 20 s of one instance's check slot; rejected documents are not counted against the database token limit; migration 0023 and these limits are untested on production-sized data and real multi-process load.

## 17. Last targeted verification before the local commit (26 Oct 2026)

Changes made during this verification (found by checking the claims, not assumed):

1. **All CPU-heavy work now happens before a run is accepted.** Building the stored result (`build_outcome`) took 1.5 s for 5,000 findings and ran after acceptance under a slot that was released when the request was cancelled. Reading, the secret check, the schema and building the result now run together in one worker thread that holds the slot until the thread has finished; after acceptance only database work is left. A busy answer, a timeout or a cancelled request therefore leaves nothing stored or counted.
2. **An unexpected worker error is a fixed `500`** ("The submission could not be checked.") with no document text; only the error type name is logged.
3. **Token creation takes the workspace lock** while counting and inserting. Before, two concurrent requests could both pass the count (this also applied to Web tokens, unchanged since before this release).
4. The audit event `app_scan.submitted` is written inside the guarded block, so a failing audit write cannot leave a queued run behind.

| Question | Evidence |
| --- | --- |
| Cancellation cannot free the slot while the thread runs | Unit test with a blocked thread (slot held after cancel, freed after the thread ends) and an end-to-end test that cancels a real HTTP request in flight (slot held until the thread is released, no run stored, nothing counted) |
| Waiting requests get the documented 503 | Test: a second request while the first is checked gets `503` with `Retry-After: 30`, nothing stored, and the slot is usable again afterwards |
| Processing timeout leaves no stored or counted run | Test: check slower than the limit gives `422 too_complex`, no run row, usage 0 |
| Oversized and complex submissions are refused before costly work | Streamed and declared size caps (413) and the value cap (`too_large`, refused before the secret scan, with a test that the scan is not called) were already tested and still pass |
| Worker exceptions and cancellation do not leak or wedge the slot | Test with a secret-shaped canary in the error: response and captured logs are clean, nothing stored, the next submission succeeds |
| Shutdown | Test: a request cancelled during a check while the application shuts down; shutdown completes once the worker thread ends (no hang, bounded by the thread, under 8 s in the test) and nothing is stored. A run already accepted when the process stops is marked interrupted at the next start (existing start-up cleanup, tested earlier) |
| Revocation or expiry before acceptance | Revocation and expiry during processing: `401`, no run, usage 0. Real race on PostgreSQL with two connections: a revocation that commits while a run waits for the workspace lock is honoured (the token is read after the lock is taken) |
| Replay cannot bypass authentication | Test: after revocation, a replay with the same key is `401`, not the stored result |
| Run already accepted | A run that was accepted completes; a request cancelled after acceptance ends `interrupted`, with no findings and no usage (test). A revocation that commits after the token check is a later event and does not undo the run |
| Token slots | 5 per scope enforced on the server: Web and App cannot take each other's slots (test), a revoked token frees only its own scope (test), a 12-thread race on PostgreSQL ends with exactly 5 Web and 5 App tokens (test). Existing Web tests unchanged |

Mutation checks (each caught by the intended test): slot released on cancellation; no `Retry-After`; worker error text passed through; no workspace lock in run acceptance; no workspace lock in token creation; cancel handler after acceptance removed. A first version of the last one targeted the browser route by mistake, which exposed a flaky test: after a cancellation the handler's background `INTERRUPTED` update and the still-running storing thread can finish in either order, and either order leaves a consistent run (all findings with a final state, or none). The test originally assumed one order and failed about half the time on SQLite when run with other files. It now waits for the interrupted state before releasing the thread. The mutant was rerun against the correct route and is caught.

Results:

| Check | Result |
| --- | --- |
| Full backend suite, PostgreSQL (before the test-only change above) | **1387 passed, 0 failed** |
| `test_appscan_ci_tokens.py` on PostgreSQL after the change, three runs | 60 passed each |
| Token, Stage 1, submission and integration tests on SQLite, three runs | 146 passed, 2 skipped (PostgreSQL-only race tests) each |
| `ruff check app alembic`, `mypy app` | clean (208 files) |
| Playwright e2e, full run | **114 passed, 0 failed** |
| `scan_secrets.py --history`, `pip-audit` | no secrets; no known vulnerabilities |

Not proven, and not claimed: behaviour with several server processes under real load (the race tests use real separate database connections in one process, and two app instances on one database in earlier tests); production-sized data; the migration lock time. **Known gap at the time, fixed afterwards:** the browser upload route (`POST /app/scans`) used the slot with `async with`, so a cancelled upload could free the slot while its thread still ran. Section 18 records the fix and its verification.

## 18. Browser upload slot fix (26 Oct 2026)

**Problem:** `POST /app/scans` held the processing slot with `async with`, so a cancelled browser upload could free the slot while its worker thread still ran.

**Change** (`backend/app/api/v1/app_scans.py`): the browser route now uses the same `_run_exclusive` helper as the CI route (slot freed by a done-callback only when the thread has finished). The helper takes `wait_seconds` and `run_seconds`; the browser route waits for a slot without limit (as before) and has a 60-second hard limit (`SCAN_HARD_SECONDS`). The worker thread only computes (`_scan_job`: start the run, scan); the handler stores the result in one atomic step. Cancelled request: the run ends `interrupted` (shielded). Hard limit: the run ends `failed`. Neither stores findings or counts. Upload size limit, five-file limit, permissions, workspace ownership, feature flag and plan checks are unchanged; Web Scanning is untouched. During the work two defects were found and fixed: keyword defaults bound at definition time (broke tests that patch the constants), and the run timeout ignoring its argument (found by the new hard-limit test).

**New tests** (`test_appscan_browser_slots.py`, 7): cancel keeps the slot until the thread ends and the run is `interrupted` with no findings or usage; a second upload cannot start work while a cancelled scan's thread runs; completion stores once and frees the slot; hard limit ends `failed`, uncounted, slot held until the thread returns; cancel while waiting for a slot takes no slot and starts no work; shutdown with a scan in flight leaves a consistent database; 413 and five-file limits still apply.

| Check | Result |
|---|---|
| New tests, repeated | 15 of 15 runs on PostgreSQL and 10 of 10 on SQLite passed |
| Mutations (new file) | caught: hard limit ignored; slot released at once; cancel handler status changed; cancel handler removed. **Not caught:** removing the `start_run` guard in `_scan_job` (it only matters in a tiny window between taking a slot and starting the thread, which cannot be hit deterministically) |
| Full backend suite, PostgreSQL | 1394 passed, 0 failed, 0 errors |
| Playwright, full | 114 passed; relevant files (targets, App Scanning, integrations) 10 passed |
| `ruff check app alembic`, `mypy app` | clean |
| `scan_secrets.py --history` | no secrets found in files or history |
| `pip-audit -r requirements.txt` | no known vulnerabilities (frontend dependencies unchanged; `npm audit` not rerun) |

**Remaining risks:** manifest parsing before acceptance runs in threads that do not hold a slot (bounded by 6 MiB and five files); limits are per instance, and multi-process or production-scale behaviour is not tested; a thread past the hard limit cannot be killed, it only keeps its slot.

## 19. GitHub Action for CI submissions (26 to 27 Oct 2026, local branch `app-scanning-action`, not pushed)

**What:** `action/app-scanning/` (`action.yml`, `submit.py`, `README.md`): a composite action that converts SARIF files from the customer's own tools into a submission and sends it to `POST /app/ci/submissions`. Standard library only; it does not install or run any scanner; no backend code changed. Tests: `backend/app/tests/test_action_app_scanning.py` and a genuine Semgrep fixture `backend/app/tests/fixtures/sarif/semgrep-1.182.1.sarif`.

### 19.1 The earlier history-scan finding
`scan_secrets.py --history` reported 1 possible secret: `docs/app-scanning-test-evidence.md:347`, rule "AWS access key id". Source: a sentence in this uncommitted section quoting AWS's published documentation example key (the value AWS prints in its own docs; it is not a credential). Checked without printing it: it is that known example (hash compared), it appears in no commit on any ref (`git log --all -S`), and no other AWS-key-shaped string exists in the working tree, the new files or the first 400 commits. **Classification: false positive; no credential was exposed, so no rotation or revocation is needed.** The sentence was reworded and the scan now reports "No secrets found in files or history". The first copy of that sentence was in a diff file sent to the owner in chat (uncommitted, never pushed).

### 19.2 Review findings and fixes (all before any commit)
| # | Finding in the first version | Fix |
|---|---|---|
| 1 | Malformed SARIF (a string where an object is expected, and similar) raised an uncaught exception; a Python traceback exits with **1**, the same code as "findings found" | Every access goes through type-safe helpers; `main` catches any unexpected error and exits **2** with a fixed message that quotes no input |
| 2 | A 201 with an empty or odd body passed the job; results such as `scanner_error` or `interrupted` could pass | Only `completed_no_findings` and `completed_findings` can pass; the answer must have a valid run id and a result, otherwise exit 2 |
| 3 | A document with 5,000 findings of 1,000-character messages exceeds the server's 4 MiB limit and would fail with 413 | Messages are shortened, then the least severe findings are dropped (binary search), with a log note |
| 4 | Deeply nested JSON raised `RecursionError`; non-regular files, binary files and files over 20 MiB were not all handled | All end in a clear exit 2; results read per file are capped at 200,000 |
| 5 | A SARIF with no run, or a tool reporting `executionSuccessful: false`, counted as a check that ran | Sent as a skipped check (result incomplete, job fails) |
| 6 | Results suppressed by the tool were sent | Left out and counted in the log |
| 7 | API address: user name, password, query and fragment were not refused; no hint when the token goes to a non-default host | Refused; a non-default host prints a warning; a Web Scanning token (`ssk_`) or a token with odd characters is refused before anything is sent |
| 8 | A `SS_NO_SLEEP` test hook lived in the shipped script | Replaced by a `sleep` parameter of `main` |
| 9 | Response read without a size bound | Bounded to 5 MiB |
| 10 | **Found only with genuine Gitleaks output (27 Oct):** Gitleaks SARIF has no `level`, so a leaked GitHub token was read as **medium** and a pipeline with `fail-on: high` would have passed | A secret finding is never below high. The finding is checked in two tests and by a mutation (floor removed, two tests fail) |

### 19.3 Results (final code)
| Check | Result |
|---|---|
| `test_action_app_scanning.py` (56 tests: conversion, 12 malformed shapes, limits, strict answers, settings, retries, genuine Semgrep, whole path through the real route) | 10 of 10 runs passed on PostgreSQL, 5 of 5 on SQLite |
| Mutations (17 in total: secret message sent, redirects followed, no mask, any api-url, incomplete ignored, unsafe paths sent, new key per attempt, any answer passes, no catch-all, suppressed sent, no size shrink, web token accepted, recursion not caught, failed tool trusted, userinfo allowed, empty id accepted, results cap off) | all caught; two weak tests were strengthened after mutations survived (302 instead of 307 for the redirect test) |
| Genuine Semgrep OSS 1.182.1 SARIF (local rules, no network; two-file sample) | converted to 2 findings (high, medium) with the right rule, file and line; the genuine file contains the matched source lines and **none** of that text is in the submission, the database or the server log |
| Genuine Gitleaks 8.18.4 (official release binary, sha256 checked against the release's published checksums; run on a throwaway folder with a randomly generated fake GitHub token, `--no-git`, **without** `--redact`) | the genuine SARIF contains the fake value in the snippet; the converted submission does not; one `github-pat` finding with rule, file `config/.env` and line 1 only; through the real route and a real socket together with the Semgrep file: exit 1 (2 high findings), and the fake value is found nowhere in the database, audit events, server log, outputs or summary. A `--redact` run of the same tool is the committed fixture `gitleaks-8.18.4-redacted.sarif` (no secret in it; the unredacted case is tested by swapping a canary for `REDACTED`) |
| Real script as a subprocess against a real local server (uvicorn, SQLite, real socket) with the genuine Semgrep file | exit 1 on the high finding; the same pipeline run again created no second run; `fail-on none` exit 0; a missing second scanner file gave result `incomplete`, exit 1; database: 3 completed + 1 incomplete runs, no source text |
| `ruff check app` and the action folder, `ruff format --check`, `mypy app`, `mypy --strict action/app-scanning/submit.py` | clean |
| `scan_secrets.py --history` | see 19.4 |
| Existing Web Scanning action tests (`test_github_action.py`) | passed; the Web action was not modified |

### 19.4 Not done and remaining limitations
- **Gitleaks:** now tested with genuine 8.18.4 output (see 19.3). Other versions or other scanners (CodeQL, Bandit, trufflehog) were not tested; the converter reads standard SARIF 2.1.0 fields only, and results without a usable rule or path are left out and counted.
- Not run on a real GitHub runner (only the script, locally; the Gitleaks binary came from the official release page and its checksum came from the same page, so the check shows the download was not corrupted, not that the release is untampered). Windows runners are not supported (`bash` and `python3` needed).
- A static-analysis rule message that interpolates matched code is sent (documented in the action README); a secret inside it makes the server refuse the whole submission (422).
- An incomplete run is accepted and counts toward the allowance (a pipeline whose scanner fails every time spends allowance; the 30 submissions per token per hour pilot limit bounds it).
- The server cannot verify that a tool ran; results are labelled as reported by the submitter.
- Sending to a non-default host is allowed (with a warning): whoever controls the workflow file can already read the secret.
- The full backend suite and Playwright were not rerun for this step: no backend or frontend code changed; one test file, a fixture and the action folder were added.
