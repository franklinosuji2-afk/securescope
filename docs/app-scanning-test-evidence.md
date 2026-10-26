# App Scanning: test evidence

Date: 26 Oct 2026. **No App Scanning code exists, so no App Scanning test has been written or run.** This file exists so that claim is explicit, and so later phases append real results here rather than rewriting history.

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
