# Implementation plan

Status key: DONE, NEXT, PLANNED.

| Phase | Scope | Status |
|---|---|---|
| 1 Audit and foundation | Layout, `/api/v1`, PostgreSQL, Alembic, readiness, Compose, audit docs | DONE (Docker build not verified) |
| 2 Authentication and multi-tenancy | Users, Argon2id, cookie sessions + CSRF, organizations, roles, audit events, cross-tenant tests | DONE (real email delivery not implemented; Docker run of this version to be confirmed) |
| 3 Target management | Targets per organization, canonical hostnames, DNS TXT and HTTP-file ownership verification with expiring challenges, scans only against verified targets | DONE (verified against mocked DNS/HTTP only; never exercised against a real domain; Docker run to be confirmed) |
| 4 Passive scanning | **NEXT.** Scanner interface; existing checks adapted; stable fingerprints; confidence; evidence capture | PLANNED |
| 5 OWASP ZAP | Baseline scan in an isolated, egress-restricted container; normalise real output | PLANNED |
| 6 Background jobs | Redis + Celery, state machine (QUEUED...TIMED_OUT), cancellation, worker-failure handling | PLANNED |
| 7 Dashboard and findings | Real metrics, history, finding lifecycle and status changes, comparisons | PLANNED |
| 8 Reporting | HTML/JSON/PDF, access-controlled downloads | PLANNED |
| 9-12 | Hardening, full test suites incl. Playwright, CI security gates (Bandit, Semgrep, Trivy), observability, commercial preparation | PLANNED |

Rules: no phase is called complete until its tests pass; anything unverified is listed as such in this file and in the README.
