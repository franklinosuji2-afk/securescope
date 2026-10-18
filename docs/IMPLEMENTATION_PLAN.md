# Implementation plan

Status key: DONE, NEXT, PLANNED.

| Phase | Scope | Status |
|---|---|---|
| 1 Audit and foundation | Layout, `/api/v1`, PostgreSQL, Alembic, readiness, Compose, audit docs | DONE (Docker build not verified) |
| 2 Authentication and multi-tenancy | Users, password hashing (argon2), cookie sessions + CSRF, organizations, roles (OWNER, ADMIN, SECURITY_ANALYST, MEMBER, VIEWER), audit events, cross-tenant tests | NEXT |
| 3 Target management | Targets per organization, canonical hostnames, approved scope, DNS TXT and HTTP-file ownership verification with expiring challenges, SSRF regression tests | PLANNED |
| 4 Passive scanning | Scanner interface; existing checks adapted; stable fingerprints; confidence; scans only against verified targets | PLANNED |
| 5 OWASP ZAP | Baseline scan in an isolated, egress-restricted container; normalise real output | PLANNED |
| 6 Background jobs | Redis + Celery, state machine (QUEUED...TIMED_OUT), cancellation, worker-failure handling | PLANNED |
| 7 Dashboard and findings | Real metrics, history, finding lifecycle and status changes, comparisons | PLANNED |
| 8 Reporting | HTML/JSON/PDF, access-controlled downloads | PLANNED |
| 9-12 | Hardening, full test suites incl. Playwright, CI security gates (Bandit, Semgrep, Trivy), observability, commercial preparation | PLANNED |

Rules: no phase is called complete until its tests pass; anything unverified is listed as such in this file and in the README.
