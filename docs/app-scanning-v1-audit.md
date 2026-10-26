# App Scanning v1: audit (decision layer)

Date: 26 Oct 2026. Phase Zero for the approved v1 decisions. **No application code, migration or configuration has been changed.** The code-level audit is `app-scanning-audit.md` (batch 30); this file adds what the v1 brief asked for beyond it and records where the approved decisions meet the existing product. Statements below were read in the repository on 26 Oct 2026; anything not verified says so.

## 1. Approved decisions (from the owner, 26 Oct 2026)

CI-first execution; OSV lookups subject to privacy and terms review; proposed allowances Free 5, Professional 100, Agency 500 App Scanning runs per month (proposed, not authority to overwrite entitlements); every component needs a licence review before release; no overall score or grade; Web Scanning and App Scanning are separate modules; global Reports section is reused; order of work: dependencies, then secrets, then SAST, then unified reports, then CI and plan enforcement.

## 2. What exists (additions to the earlier audit)

| Area                           | Verified finding                                                                                                                                                                                                                                                                | Evidence                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Plans                          | Three customer plans plus an internal plan, one catalogue. Fields: `max_websites`, `scans_per_month`, `history_days`, `can_invite`, `client_workspace`, `scheduled_scans`                                                                                                       | `billing/plans.py`                                                          |
| Web allowances today           | Free 3, Professional 30, Agency 150 scans per month                                                                                                                                                                                                                             | `billing/plans.py`, `docs/PLANS.md`                                         |
| Usage accounting               | Counts `ScanRow` rows since 00:00 UTC on the 1st, except failed scans; checked in the same transaction as the insert, with a row lock on PostgreSQL                                                                                                                             | `repositories/plans.py` `usage`, `docs/PLANS.md`                            |
| CI access                      | The GitHub Action and API tokens are gated by `scheduled_scans`, which **Free does not have**                                                                                                                                                                                   | `api/v1/ci.py` (`start_ci_scan`), `api/v1/integrations.py`, `docs/PLANS.md` |
| Billing                        | No payment provider is connected. The `subscriptions` and `billing_events` tables exist, nothing writes them. Prices are hypotheses, "not charged yet"                                                                                                                          | `docs/PLANS.md` "Not built yet"                                             |
| Downgrade preview              | Compares usage with the target plan's limits for sites, scans, history, schedules and tokens                                                                                                                                                                                    | `billing/preview.py`                                                        |
| GitHub Action                  | Bash script on the customer's runner: token from the environment, masked, passed to curl through stdin config, never in the process list; scanned text is cleaned before logging; exit codes 0, 1, 2; retries on connection errors and 502 to 504. It scans a **URL**, not code | `action/scan.sh`, `action/action.yml`                                       |
| File uploads                   | None anywhere                                                                                                                                                                                                                                                                   | earlier audit, section 2                                                    |
| Privacy notice and legal state | Legal pages exist; transfer mechanisms and some provider facts are flagged "not verifiable from the repository"; no mention of any vulnerability database                                                                                                                       | `docs/legal-audit.md`                                                       |
| Repository tooling             | CI already runs Bandit, pip-audit, Semgrep and a secret-pattern scan on this repository                                                                                                                                                                                         | `.github/workflows/ci.yml`                                                  |

## 3. What the audit changes about the brief

1. **Free cannot use CI today.** The proposed Free allowance of 5 runs is only usable through browser manifest upload, unless the owner decides Free also gets CI tokens for App Scanning (a plan change, see `app-scanning-v1-plan-entitlements.md`).
2. **The proposed App Scanning allowances are not like for like with Web Scanning.** 5, 100 and 500 runs sit beside 3, 30 and 150 web scans. A "run" is cheap on our side (parse, one batched lookup, store), but the unit must be defined before any number is set.
3. **No billing exists to bill against.** Allowances can be enforced server-side, but nothing is sold; prices and what each plan "includes" in public pages must not mention App Scanning until it works.
4. **The existing Action is a web scan.** App Scanning needs a second mode or a second action; it cannot be a flag on the current script without risking the web exit-code behaviour.
5. **Counting must not touch `ScanRow`.** Web usage counts `ScanRow`; App Scanning needs its own counter so one cannot consume the other, and so the web numbers shown on the Account page do not change.

## 4. Ranked findings (risk and user value)

| Rank | Item                                                      | Why                                                                         |
| ---- | --------------------------------------------------------- | --------------------------------------------------------------------------- |
| 1    | Secret redaction guarantee (new module, canary tests)     | Critical risk; it gates everything that carries file content                |
| 2    | Free versus CI plan conflict                              | Blocks a coherent plan design                                               |
| 3    | OSV terms, data licence and privacy disclosure unverified | Release blocker; official documentation was not reachable from this session |
| 4    | Unit definition of a "run" and its counter                | Needed before any limit is enforced                                         |
| 5    | Separate tables and routes, no web table changes          | Protects Web Scanning                                                       |
| 6    | Strict CI submission schema and server re-check           | Anything posted by CI is untrusted input                                    |
| 7    | Second Action mode with the same token handling           | User value, after the above                                                 |

## 5. Not verified in this session

- The official OSV API documentation and terms (the documentation hosts were not reachable here). Everything about OSV in the other v1 documents is therefore **unverified** and marked accordingly.
- Licences of Semgrep rules, any secret scanner and its rules, and any container image.
- Legal conclusions of any kind.

## 6. Implementation plan (smallest safe steps, each a separate batch)

| Step | Content                                                                                              | Needs before start                                            |
| ---- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| A    | Documentation set (this batch)                                                                       | Owner review                                                  |
| B    | Redaction module and canary test harness, no feature                                                 | none. Built in batch 32 (see `app-scanning-test-evidence.md`) |
| C    | Manifest parsers and result model, tables, plan counter, behind a disabled flag, mocked lookups only | Decisions D1 to D4                                            |
| D    | OSV client, enabled only after the privacy and terms gates are cleared                               | Gate G1                                                       |
| E    | Secret findings through CI submission                                                                | B, licence review of the chosen tool                          |
| F    | SAST findings through CI submission                                                                  | Licence review of tool and rules                              |
| G    | Unified findings view, reports, history                                                              | C                                                             |
| H    | Action mode, tokens, plan enforcement                                                                | Decision on Free and CI                                       |

Nothing in B to H is started.
