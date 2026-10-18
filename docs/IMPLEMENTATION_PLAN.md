# Implementation plan

Status key: DONE, NEXT, PLANNED.

| Phase | Scope | Status |
|---|---|---|
| 1 Audit and foundation | Layout, `/api/v1`, PostgreSQL, Alembic, readiness, Compose, audit docs | DONE (Docker build not verified) |
| 2 Authentication and multi-tenancy | Users, Argon2id, cookie sessions + CSRF, organizations, roles, audit events, cross-tenant tests | DONE (real email delivery not implemented; Docker run of this version to be confirmed) |
| 3 Target management | Targets per organization, canonical hostnames, DNS TXT and HTTP-file ownership verification with expiring challenges, scans only against verified targets | DONE (HTTP-file verification confirmed on one real domain; DNS TXT path mock-tested only; full Docker Compose stack runs, confirmed by hand) |
| 4 Passive scanning | **NEXT.** Scanner interface; existing checks adapted; stable fingerprints and confidence (done in v0.5); evidence capture (done) | PARTIAL |
| 5 OWASP ZAP | Baseline scan in an isolated, egress-restricted container; normalise real output | PLANNED |
| 6 Background jobs | Redis + Celery, state machine (QUEUED...TIMED_OUT), worker-failure handling. In-process cancel and retry exist since v0.7 | PARTIAL |
| 7 Dashboard and findings | Real metrics, history, finding lifecycle and status changes (backend and API done in v0.5; UI in progress), comparisons | PARTIAL |
| 8 Reporting | HTML/Markdown/JSON/PDF export, access-controlled (PDF done in v0.7); stored reports not planned yet | PARTIAL |
| 9-12 | Hardening, observability, commercial preparation. Playwright e2e and CI security gates (Bandit, pip-audit, npm audit, Semgrep, Trivy) are already in place (Semgrep/Trivy unverified until first CI run) | PARTIAL |

Rules: no phase is called complete until its tests pass; anything unverified is listed as such in this file and in the README.
