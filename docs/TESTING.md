# Testing

```bash
cd backend
pytest                                   # SQLite
SECURESCOPE_TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/test pytest   # PostgreSQL (schema is dropped!)
ruff check . && ruff format --check . && mypy app

cd ../frontend && npm test && npm run lint && npm run typecheck && npm run build
```

Backend (217 tests, no internet): domain targets and ownership verification (hostname normalisation, DNS and HTTP challenges incl. mismatches, expiry, regeneration, rate limit, cross-tenant and role checks, scan gating, audit), target validation and SSRF, fetcher and redirects, checks and scoring, reports (escaping), repositories and migrations, auth (cookies, CSRF, origin check, rate limits, reset/verification, audit), tenancy and roles (cross-tenant reads, spoofed organization header, escalation attempts, last-owner rule). Frontend (21 tests): routing, sign-in gating, forms, CSRF/organization headers, role-based UI, team page, targets page (instructions, failure messages, confirm-before-remove, viewer view).

**End-to-end (Playwright, real Chromium, real backend, no mocks):** `cd frontend && npx playwright install chromium && npm run e2e`. It starts the backend (SQLite by default, `E2E_DATABASE_URL` for PostgreSQL) and the built frontend itself. 5 tests: scan refused for an unverified domain with a link to Targets, invalid and valid target registration, honest failed verification, confirm-before-remove, cross-account isolation, axe-core (WCAG 2.0/2.1 A and AA) on every public and signed-in page failing on serious or critical violations, skip link. Automated axe checks find only part of the accessibility problems; no screen-reader or manual keyboard audit has been done.

**CI** (`.github/workflows/ci.yml`): backend (PostgreSQL service, ruff, mypy, pytest), frontend, e2e (PostgreSQL), docker build, and a `security` job: Bandit, pip-audit, npm audit (high+), Semgrep (`p/python`, `p/owasp-top-ten`, `p/typescript`) and Trivy 0.58.0 (`fs`: vulnerabilities, secrets, Dockerfile/Compose misconfiguration, HIGH/CRITICAL, unfixed ignored). Verified locally: Bandit (no issues), pip-audit and npm audit (none known), Playwright. **Not verified locally:** Semgrep and Trivy (their rule registry / image are not reachable from the build environment), so their first CI run may report findings that need triage. Container image scanning is not done.
