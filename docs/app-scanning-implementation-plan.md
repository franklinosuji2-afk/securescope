# App Scanning: implementation plan

Date: 26 Oct 2026. Nothing below is built. Each phase is a separate batch, reviewed and approved by the owner before the next starts. No phase deploys by itself; no production migration runs without approval.

Rule for every phase: the existing Web Scanning test suite runs unchanged and must stay green, and the diff is reviewed before it is offered.

## Phase 1: design sign-off (this batch)

- **Goal:** agree the architecture, the security model and the owner decisions.
- **Files:** `docs/app-scanning-*.md` only.
- **Security:** none (documents).
- **Smallest increment:** the five documents.
- **Tests:** none apply; see `app-scanning-test-evidence.md` for what is and is not evidenced.
- **Remaining risk:** every decision below is still open.

## Phase 2: dependency scanning from manifest files

- **Goal:** a signed-in user uploads `package-lock.json`, `package.json` or `requirements.txt` and sees accurate dependency findings, with honest limits.
- **Files to change:**
  - new: `backend/app/appscan/{manifests,vulndb,normalise,redaction}.py`, `models/app_scan.py`, `schemas/app_scan.py`, `repositories/appscans.py`, `api/v1/app_projects.py`, `api/v1/app_scans.py`, one Alembic migration (additive), tests and fixtures;
  - edited: `billing/plans.py` and `entitlements.py` (new fields), `main.py` (router registration), `api/v1/audit.py` (event names), `frontend/src/App.tsx` (nav), new pages and a small API client.
- **Security:** T1, T2, T3 (reject archives), T4, T5, T6, T7 (redaction module), T8, T9, T10, T11, T16.
- **Smallest increment:** npm lockfile v2 or v3 and `requirements.txt` with pinned versions only; one project, one scan, a findings table, the limitations block. Unpinned ranges are reported as "unsupported: no exact version", not guessed.
- **Regression tests:** parser fixtures (valid, malformed, oversized, nested, unsupported); mocked database responses (found, none, partial, unavailable → incomplete); cross-customer and role tests; plan-limit tests; canary secret; outbound payload test; Web Scanning suite; migration up and down on a scratch database.
- **Prerequisites:** owner decisions 2, 3, 5, 6. Real OSV responses must be checked first to confirm severity and fixed-version fields (not verified yet).
- **Remaining risk after the phase:** third-party data disclosure, advisory lag, no source analysis.

## Phase 3: static analysis and secret detection through CI

- **Goal:** results from established tools run on the customer's runner appear in SecureScope.
- **Files:** new `POST /api/v1/ci/app-scan` accepting a strict normalised schema; converters for Semgrep, Bandit and a secret scanner (published with the Action, not run by the server); `action/` mode switch; schema docs.
- **Security:** T7 (server re-check of secrets), T12, T13. No source reaches the server.
- **Smallest increment:** one SAST tool and one secret tool, converted and submitted; stored and shown with the same finding view.
- **Tests:** schema fuzz; forged oversized and injected submissions; secret re-check rejection without echo; HTML and PDF escaping; converter tests on recorded tool output fixtures (no tool is downloaded in the tests).
- **Prerequisites:** Phase 2 accepted, licence review (decision 4).
- **Remaining risk:** the server cannot prove a tool actually ran.

## Phase 4: reports, history and comparison

- **Goal:** PDF and JSON reports; compare two scans of a project (new, fixed, still open); retention.
- **Files:** `reporting/app_report.html`, a context builder beside `pdf.py`, comparison endpoint, history page, retention job.
- **Security:** T7 in PDFs and JSON, T15.
- **Smallest increment:** one PDF with sections from architecture 7, one comparison view.
- **Tests:** report text contains scanner and database versions and the limits; canary secret absent from PDF text; web report output unchanged (byte-level golden test of an existing sample).
- **Remaining risk:** very large reports on the 512 MB instance (measured, not assumed).

## Phase 5: CI thresholds and tokens

- **Goal:** `fail-on` severity in the Action, clear exit codes, token scope for App Scanning.
- **Files:** `action/`, `api/v1/ci.py`, token scope field and migration.
- **Security:** T14; default never fails; no broad repository permission is requested.
- **Tests:** exit-code table; token without scope → 403; no secret in the Action log (canary).
- **Remaining risk:** customers misconfigure thresholds; documented.

## Phase 6: container and infrastructure files

- **Goal:** Dockerfile, Compose, Kubernetes and Terraform checks through established tools run in CI.
- **Files:** converters and rule documentation only, on the Phase 3 path.
- **Smallest increment:** Dockerfile and Compose via one tool; others only if justified by demand.
- **Not started until:** Phases 2 to 5 have real use. It is not added to increase the feature count.

## Phase 7: controlled pilot and operational readiness

- **Goal:** real use by a few authorised users on their own code; measure accuracy, false positives, load and support burden.
- **Work:** pilot agreement, privacy notice, runbook, alerting, load and abuse test on the real instance size, an independent review, and the decision on an isolated worker if server-side source handling is wanted.
- **Exit:** a written go or no-go; nothing is assumed ready.

## Owner decisions needed before Phase 2

1. CI-first (recommended) versus a paid isolated server worker.
2. Permission to use the public OSV database, and the privacy notice wording.
3. Which plans include App Scanning and the monthly allowance.
4. Licence verification of any rule sets and databases.
5. No score or grade in the first release.
6. Menu and marketing names.

## Not in scope

Dynamic testing, penetration testing, auto-upgrade, auto-rotation, repository cloning, GitHub App, archive extraction.
