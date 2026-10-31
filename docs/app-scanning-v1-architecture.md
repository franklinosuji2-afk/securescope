# App Scanning v1: architecture

Date: 26 Oct 2026. A design; **nothing is implemented.** Detail on tables, components and states is in `app-scanning-architecture.md` and `app-scanning-security-model.md`; this file records the v1 decisions and what changed.

## 1. Execution model (decided: CI-first)

| Component                                   | Runs where         | Gets                                                                      | Sends                                                                                                                         |
| ------------------------------------------- | ------------------ | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Customer's CI job (the Action, second mode) | Customer's runner  | Their own checkout                                                        | A bounded JSON document of normalised, redacted findings and, for dependencies, a list of package ecosystem, name and version |
| SecureScope API                             | Our infrastructure | The JSON document, or manifest files uploaded in the browser (parse only) | Nothing about the customer's code leaves it except package coordinates to the dependency database (see privacy document)      |
| Hosted scanning                             | Not built          |                                                                           | Separate review required                                                                                                      |

The scanner on the runner must: run only named tools, never project scripts (no install, build, test, lifecycle hooks), have file-count, size and time limits, avoid network access except to SecureScope (and the vulnerability database if the runner does lookups, see D-A), redact before transmission, authenticate with the existing bearer token, send only to the workspace the token belongs to, retry safely (idempotency key per run), and never print the token (same pattern as `action/scan.sh`: masked, passed through stdin to curl).

Open design point **D-A: who calls the dependency database.** Option 1, the server calls it from submitted coordinates: one consistent privacy statement, one cache, one place that turns failures into "incomplete". Option 2, the runner calls it: our data flow shrinks, but results depend on customer-side tooling and the disclosure becomes the customer's. Recommendation: Option 1. The owner decides after the privacy review.

## 2. Order of capabilities (as approved)

1. Dependency vulnerability scanning (manifest parsing, lookup, normalisation).
2. Secret detection (customer-side tool, server re-check, no value ever stored).
3. SAST (customer-side established tool; no custom rule engine).
4. Unified findings and reports.
5. Action mode, tokens and plan enforcement.

This reorders the earlier plan, which put SAST and secrets together; they are now separate steps and secrets come first because the redaction guarantee is the riskiest part.

## 3. Results model

Separate tables (`app_projects`, `app_scans`, `app_findings`, `app_finding_states`), sharing the severity, confidence and status enums. No web table changes. No score or grade anywhere: not in the schema, API, UI or PDF (a test asserts the response contains no `score` or `grade` key).

Scan states shown to users, never merged:

| State                                                  | Meaning                                                                |
| ------------------------------------------------------ | ---------------------------------------------------------------------- |
| Completed, findings detected                           | The selected checks ran and found something                            |
| Completed, no findings detected by the selected checks | Wording always names the checks and carries the limitations block      |
| Incomplete                                             | A check or data source was unavailable or skipped; lists which and why |
| Scanner error                                          | A tool failed; fixed message, no raw tool output                       |
| Unsupported input                                      | Format or version not handled                                          |

An unavailable dependency lookup is **Incomplete**, never clean.

## 4. Navigation

Primary: Dashboard, Web Scanning, App Scanning, Scan History, Reports, Clients & Teams, Settings. Within App Scanning: Overview, Projects, Findings, Scan History, Integrations. Reports stays the single global section; App Scanning reports are listed there, labelled by type. The current `NAV` has no "Web Scanning" grouping, so a navigation change touches existing menu structure and gets its own batch with the existing axe and e2e tests re-run.

## 5. Dependency scanning scope (v1)

Formats proposed: `package-lock.json` (v2 and v3), `package.json` (exact versions only), `requirements.txt` (pinned `==` only). Anything else is Unsupported input. Ecosystems for lookup: `npm` and `PyPI` (names as OSV uses them; **unverified** until the official documentation is read). Unpinned ranges are not guessed.

## 6. What v1 does not do

Hosted or server-side code analysis, archives or repository upload, GitHub App, container and infrastructure scanning, dynamic testing, auto-upgrade, auto-revocation, any overall score.

## 7. Dependencies between decisions

D-A (who calls OSV), D1 to D4 in the entitlements document, and gate G1 in the privacy document must be settled before step D of the implementation plan.

## 8. Dependency scan result rules (built in batch 35, tested with fake sources only)

The scan depends on a `VulnerabilitySource` interface (`appscan/vulns.py`). Since 31 Oct 2026 an OSV client exists (`services/osv.py`, decision D-A option 1), used only when `SECURESCOPE_APP_OSV_ENABLED` is set; it stays off in deployments until gates G1 and G3 close.

| Situation                                                                            | Status                                              | Why                                                                                                                                                                   |
| ------------------------------------------------------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every package checked, source answered for all, nothing unsupported                  | Completed (with or without findings)                | Findings never make a run unsuccessful                                                                                                                                |
| Source gave no answer for some packages                                              | Incomplete                                          | Names how many were not checked                                                                                                                                       |
| Entries the parser could not check (ranges, addresses, options)                      | Incomplete                                          | Never described as clean while part of the list is unchecked. A `package.json` with ranges is therefore always incomplete; a lockfile is the way to a complete result |
| Time budget (default 60 s) ran out                                                   | Incomplete                                          | Remaining batches count as not answered                                                                                                                               |
| More than 5 000 findings                                                             | Incomplete                                          | Extra findings are cut and the cut is stated                                                                                                                          |
| Source unreachable for everything, or a reply that does not line up with the request | Failed (not charged)                                | Nothing was checked                                                                                                                                                   |
| No checkable package in the files                                                    | Failed (not charged)                                | An empty list is not a clean result                                                                                                                                   |
| Source raises any error                                                              | Treated as unavailable; the error text is discarded | A broken source degrades the scan and cannot leak content                                                                                                             |

Advisory text is untrusted: control characters are removed, text is redacted and capped (500 characters), only `https://` reference links of sane length are kept, fixed versions and ids must match a strict pattern, and an advisory whose id does not match is dropped. A missing severity is shown as Medium with the sentence "The advisory source did not give a severity", not invented as certain. Remediation text never changes dependencies.
