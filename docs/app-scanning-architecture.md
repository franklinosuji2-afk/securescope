# App Scanning: architecture

Date: 26 Oct 2026. A design, not an implementation: **no App Scanning code exists yet.** Read `app-scanning-audit.md` first for the evidence behind these choices.

## 1. Principles

1. **Web Scanning is not touched.** No web table, route, report or test changes shape. App Scanning is added next to it.
2. **Never run or analyse customer code on the API server.** The server may parse small data files (manifests) and receive already-redacted results. Anything that reads source code runs on the customer's own runner, or in a separate isolated worker that does not exist yet.
3. **The server never stores source code.** It stores findings, file names, line numbers and digests.
4. **Reuse what exists:** sign-in, workspaces and roles, plans, audit log, rate limits, the report building blocks and the CI token.
5. **Be honest about coverage.** Every scan records what ran, what was skipped and why, and which database or scanner version answered.

## 2. Two kinds of input

| Path                                             | What the server receives                                                                                          | Where the work happens                                                                                                   | First release                                         |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| **A. Manifest upload**                           | One to five small files (`package-lock.json`, `package.json`, `requirements.txt`) pasted or chosen in the browser | Parsed on the server by strict, execution-free parsers; package names and versions looked up in a vulnerability database | **Yes** (Phase 2)                                     |
| **B. CI submission**                             | A JSON document of normalised findings produced by established tools running in the customer's own GitHub Action  | On the customer's runner; the server only validates, re-checks for secrets, stores and reports                           | Phase 3                                               |
| **C. Repository or archive upload / GitHub app** | Source code                                                                                                       | An isolated worker that does not exist                                                                                   | **No** (needs owner approval and paid infrastructure) |

Path B means the code never reaches SecureScope. The customer already trusts their own runner with their code, the existing Action already works the same way, and there is no server-side attack surface from untrusted code.

## 3. Components

```
Browser ──upload manifests──► API (parse only) ──► vulnerability database (fixed host)
GitHub Action ──normalised findings──► API (validate, redact check) ──► database
                                          │
              app_projects / app_scans / app_findings / app_finding_states
                                          │
                 reports (PDF, JSON) ◄────┘   audit log, plans, rate limits (shared)
```

Backend modules (provisional):

- `appscan/manifests.py`: parsers. Input: bytes and a file name. Output: a list of `(ecosystem, name, version, source file, line)` and a list of unsupported items. No execution, no network, no file system writes.
- `appscan/vulndb.py`: the only network client. Fixed host (a constant), HTTPS only, no redirects, request and response size caps, timeouts, batch size cap. Returns advisories or an explicit `unavailable`.
- `appscan/normalise.py`: turns advisories and CI submissions into the common app finding.
- `appscan/redaction.py`: the one place that decides what text may be stored. Used on every write and re-checked on CI submissions.
- `repositories/appscans.py`: all queries, each taking the organization id.
- `api/v1/app_projects.py`, `app_scans.py`: routes using the existing `require(Permission.…)` dependencies.
- `reporting/app_report.html` and a context builder next to `pdf.py`.

Frontend: a new "App Scanning" entry in `NAV`, pages Projects, New app scan, Findings and Scan history, built from existing components and tokens; each state in section 6.

## 4. Data model (additive migrations only)

| Table                | Key columns                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app_projects`       | id, organization_id, client_id (optional), name, source (`manifest` or `ci`), created_by, created_at, archived_at. Unique per organization and name                                                                                                                                                                                                                                                                            |
| `app_scans`          | id, organization_id, project_id, requested_by, token_id (CI), kinds (`dependency`, `sast`, `secrets`), status (`queued`, `running`, `completed`, `incomplete`, `failed`), scanners (JSON list of name, version, data timestamp), inputs (JSON: file name, size, sha256; never content), checks_run, checks_skipped (with reason), error (fixed sentences), ref (branch or commit label, optional), idempotency key, timestamps |
| `app_findings`       | id, scan_id, position, kind, rule_id, title (fixed text per rule), severity, confidence, category, description, remediation, path, line, package ecosystem / name / version, fixed versions, advisory ids and references, evidence (redacted), fingerprint                                                                                                                                                                     |
| `app_finding_states` | organization_id, project_id, fingerprint, status, note, first/last seen, resolved, updated by. Same lifecycle as web findings                                                                                                                                                                                                                                                                                                  |

Fingerprints: `sha256(project | kind | advisory-or-rule id | package or normalised path)`; line numbers are excluded so a moved line is not a new finding.

Status meanings (shown separately in the interface and in reports):
**Completed, findings detected** · **Completed, no findings from these checks** · **Incomplete** (a check or data source was unavailable) · **Failed** (scanner error) · **Unsupported** (file format not handled).

No score or grade in the first release; counts per severity and a plain risk label only.

## 5. Permissions, plans and limits

- Reuse permissions: `SCAN_READ` to view, `SCAN_CREATE` to upload or submit, `REPORT_EXPORT` for reports, `FINDING_TRIAGE` to change finding status. A viewer cannot start scans.
- New plan fields in `billing/plans.py` (proposal, values for the owner to set): `app_scanning` (yes or no), `app_projects`, `app_scans_per_month`. Checked in `Entitlements`; Free is a decision for the owner.
- Input limits, enforced on the server: at most 5 files per scan, 2 MB per file, 6 MB per request, 20 000 packages per scan, JSON nesting depth 64. Over a limit: a clear 413 or 422, nothing stored.
- One app scan at a time per instance (its own semaphore), a per-workspace rate limit, and a monthly allowance, in the same style as web scans.
- Retention follows `history_days` of the plan; findings only, no source.

## 6. Interface states

Loading, empty (no projects), validation error (file too big, unsupported type, unreadable), success with findings, success with none (with "from these checks" wording and the limitations block), incomplete (which check, why, what to do), failed, and a permission-denied state for viewers. Mobile layout and light and dark themes follow the existing patterns and the same axe tests.

## 7. Reports

A separate template reusing the cover, risk wording and severity colours. Sections: project and identity, date, scan kinds, scanner and database versions, files examined (name, size, digest), checks run and skipped, findings with redacted evidence and remediation, incomplete checks, and limits. The report states it covers only the checks listed; it never mixes web and code findings.

## 8. CI (Phase 3 and 5)

The existing token and Action are extended with a second mode. The Action runs chosen tools (dependency audit, Semgrep or Bandit, a secret scanner) on the runner, converts their output with a small published converter, and posts it. Thresholds (`fail-on`) are configured in the workflow file and default to never failing. The server enforces plan, token scope and rate limit, validates the schema strictly, and refuses evidence that looks like a secret. A token created for web scans can be given App Scanning access only explicitly.

## 9. What is deliberately not built

Active or dynamic testing, penetration testing, automatic upgrades, automatic credential rotation, repository cloning, archive extraction, a GitHub App, and container or infrastructure scanning before the earlier phases are proven.
