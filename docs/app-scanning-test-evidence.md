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
