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
