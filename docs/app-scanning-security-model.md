# App Scanning: security model

Date: 26 Oct 2026. A design, not an implementation: **none of these controls exist in code yet.** Each row says which phase delivers it and which test proves it. Nothing here is a claim that the module is safe; it is the standard the module must meet before each readiness level.

## 1. Assets and trust boundaries

| Asset                                          | Sensitivity                       | Where it may live                                                               |
| ---------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------- |
| Uploaded manifest file bytes                   | Medium (private package names)    | Request memory only. Never written to disk or the database                      |
| Digests, names, sizes of inputs                | Low                               | `app_scans.inputs`                                                              |
| Findings (rule, file, line, package, advisory) | Medium                            | `app_findings`, scoped by organization                                          |
| Evidence text                                  | High if it could contain a secret | Only after redaction (section 4)                                                |
| Source code                                    | High                              | **Never reaches the server** in the first release                               |
| API tokens, production secrets                 | Critical                          | Environment of the API process only. No scanner, parser or worker may read them |

Boundaries: browser to API (authenticated, authorised); CI runner to API (bearer token); API to vulnerability database (fixed host, outbound only). There is no boundary where customer code is executed, because no code is executed.

## 2. Threats and controls

| #   | Threat                                                                       | Control                                                                                                                                                                          | Phase                             | Proving test                                                                                                                                                                                        |
| --- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1  | Hostile manifest (huge, deeply nested, crafted)                              | Size caps (2 MB per file, 6 MB per request), JSON depth cap, package cap, standard-library parsers only, no `eval`, no `pickle`, no YAML tags, hard time limit                   | 2                                 | Oversized, nested, malformed, and fuzz-style fixtures all end in a clean 4xx with nothing stored                                                                                                    |
| T2  | Execution of project code                                                    | Parsers read data only. No install, build, import or script step anywhere. The code path has no subprocess                                                                       | 2                                 | A fixture with install scripts and a `postinstall` hook; the test asserts no subprocess call and no file written (patched `subprocess` and a read-only temp directory)                              |
| T3  | Archive attacks (zip slip, bombs, symlinks)                                  | Archives are rejected in the first release (extension and magic bytes). Any later archive support needs the isolated worker and its own review                                   | 2 (reject), later                 | Zip and tar fixtures are refused                                                                                                                                                                    |
| T4  | SSRF through the vulnerability client                                        | Destination is a constant. No user input in scheme, host, port, path prefix. HTTPS only, redirects off, response size and time caps, no proxy variables honoured for other hosts | 2                                 | Test with a mocked transport asserts the host; user-supplied URLs in the body are ignored and never fetched                                                                                         |
| T5  | Cross-customer access                                                        | Every query takes the organization id. 404 for other workspaces. New routes are added to the existing route-coverage test                                                        | 2                                 | Cross-customer test for projects, scans, findings, reports                                                                                                                                          |
| T6  | Privilege misuse                                                             | Reuse `SCAN_READ`, `SCAN_CREATE`, `REPORT_EXPORT`, `FINDING_TRIAGE`. A viewer cannot create; a member cannot triage if the matrix says so                                        | 2                                 | Role matrix test for each route                                                                                                                                                                     |
| T7  | Secret leakage through findings, logs, errors, reports, webhooks, emails     | Redaction rule in section 4; evidence for secret findings is never a value; log lines carry ids and counts only; error bodies are fixed sentences                                | 2 (redaction module), 3 (secrets) | Canary-secret test: a unique fake secret is injected at every input point and the test asserts it is absent from DB rows, API responses, PDF text, webhook payloads, alert emails and captured logs |
| T8  | Denial of service on the 0.1 CPU instance                                    | Hard caps, one app scan at a time (own semaphore), per-workspace rate limit, monthly allowance, request body limit before parsing                                                | 2                                 | Concurrency and limit tests; a load run recorded in the test evidence                                                                                                                               |
| T9  | False reassurance                                                            | Result states in architecture section 4; "no findings from these checks" wording; limitations block on screen and in reports; unavailable data is **incomplete**                 | 2                                 | Mocked vulnerability database failure yields `incomplete`, never `completed, no findings`                                                                                                           |
| T10 | Data leaving the platform (package names to a third party)                   | Fixed destination, only name and version sent (no file names, no project name, no organization), documented in the privacy notice, owner approval first                          | 2 (after approval)                | Test asserts the outbound payload contains only ecosystem, name, version                                                                                                                            |
| T11 | Stale or wrong advisory data                                                 | Record the database timestamp or version in every scan; show it; warn when older than a set age                                                                                  | 2                                 | Fixture with an old timestamp shows the warning                                                                                                                                                     |
| T12 | Scanner supply chain                                                         | Pinned versions with hashes, licence check before shipping, version recorded per scan                                                                                            | 3                                 | CI pin check; licence file reviewed                                                                                                                                                                 |
| T13 | Malicious CI submission (forged findings, oversized, injection into reports) | Strict schema with length limits, enum severities, rejection of unknown fields, output escaped in HTML and PDF, per-token rate limit, server-side secret re-check                | 3, 5                              | Schema fuzz tests; an XSS payload in a title renders as text in the page and the PDF                                                                                                                |
| T14 | Token abuse                                                                  | Existing token model; App Scanning scope must be granted explicitly; revocation works immediately                                                                                | 5                                 | Token without scope receives 403                                                                                                                                                                    |
| T15 | Retention and deletion                                                       | Findings follow `history_days`; project deletion removes its scans and findings; no source is held, so nothing else to delete                                                    | 4                                 | Deletion test; retention job test                                                                                                                                                                   |
| T16 | Audit gaps                                                                   | Events: project created or archived, scan started, completed, failed, finding status changed, report exported, CI submission accepted or rejected. Ids and counts only           | 2                                 | Audit test per event                                                                                                                                                                                |

## 3. Execution isolation

First release (Phases 1 to 5): **no isolation boundary is needed because nothing is executed and no source is processed on the server.** This is a deliberate design choice, not an omission.

Required before any of the following is enabled (each needs the owner's approval of the infrastructure and a separate review):

- repository or archive upload;
- any server-side code analyser (Semgrep, Bandit or similar run by SecureScope);
- any server-side secret scan of file contents.

Minimum boundary for that future worker: a separate process in its own container or microVM, no shared filesystem with the API, read-only root, a per-job empty working directory deleted afterwards, a non-root user, no production environment variables, CPU, memory, time and output-size limits, **no network** (rules and databases baked in at build time), no access to internal addresses or metadata endpoints, a queue instead of in-process calls, and results returned as a bounded JSON document that the API validates like a CI submission. This is documented so the decision can be priced; it is not built.

## 4. Secret handling rule

1. A secret value, or any part of it, is **never** stored, logged, returned, emailed, put in a webhook or rendered in a report. Not truncated, not masked with some characters left.
2. A secret finding keeps: the rule name, file path, line number, a length class (for example "20 to 40 characters"), and a keyed hash (HMAC with a server key) used only to recognise the same finding next time.
3. Evidence for any finding passes through the redaction module before it is stored. The module drops, rather than masks, anything matching the secret patterns already used in `scripts/scan_secrets.py` plus entropy-based candidates.
4. CI submissions are re-checked on the server with the same patterns. A match rejects the whole submission with a fixed message that does not echo the content.
5. Remediation text is fixed: revoke and rotate the credential at its provider, remove it from history, check for misuse. SecureScope never revokes or rotates anything.
6. File paths are shown, but a path that itself looks like a secret is redacted.
7. Webhook and alert payloads for App Scanning carry counts and severities, never titles that could embed content.

## 5. Plan and abuse limits (proposal)

Values are for the owner to set; the table shows what is enforced on the server whatever the numbers are.

| Limit                                                                | Enforced where                                |
| -------------------------------------------------------------------- | --------------------------------------------- |
| Files per scan, bytes per file, bytes per request, packages per scan | Route and parser, before work starts          |
| Projects per workspace                                               | Entitlements                                  |
| App scans per month                                                  | Entitlements, same counter style as web scans |
| Concurrent app scans                                                 | Semaphore (1 on the free instance)            |
| Scans per project per hour                                           | Rate limiter                                  |
| History retention                                                    | `history_days`                                |

## 6. Residual risks even after the controls

- Package names are sent to a third party (T10): reduced to name and version, still disclosed.
- Advisory databases are incomplete and lag disclosures; a clean result is only "nothing known to the database used".
- Manifest-only scanning cannot see vulnerable code that is not a dependency, or dependencies that are not declared.
- CI submissions are produced by software the customer controls; the server can validate shape and redaction, but cannot verify that the tool really ran.
- In-memory rate limits are per instance and reset on restart.

## 7. Gate for each readiness level

| Level              | Must hold                                                                                                                                                                        |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Local prototype    | Phase 2 merged on a branch; all tests in this document for T1, T2, T4, T5, T6, T7, T9 pass locally                                                                               |
| Controlled testing | Plus owner decisions 1, 2 and 5 made, privacy notice updated, canary-secret test passing, load result recorded                                                                   |
| External pilot     | Plus the CI path (T13, T14), retention (T15), licences checked (T12), abuse test, a rollback plan                                                                                |
| Commercial release | Plus billing and plan values live, support and incident procedure, an independent security review, and, if any source is processed server-side, the isolated worker of section 3 |
