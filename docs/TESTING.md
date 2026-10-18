# Testing

```bash
cd backend
pytest                                   # SQLite
SECURESCOPE_TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/test pytest   # PostgreSQL (schema is dropped!)
ruff check . && ruff format --check . && mypy app

cd ../frontend && npm test && npm run lint && npm run typecheck && npm run build
```

Backend (217 tests, no internet): domain targets and ownership verification (hostname normalisation, DNS and HTTP challenges incl. mismatches, expiry, regeneration, rate limit, cross-tenant and role checks, scan gating, audit), target validation and SSRF, fetcher and redirects, checks and scoring, reports (escaping), repositories and migrations, auth (cookies, CSRF, origin check, rate limits, reset/verification, audit), tenancy and roles (cross-tenant reads, spoofed organization header, escalation attempts, last-owner rule). Frontend (21 tests): routing, sign-in gating, forms, CSRF/organization headers, role-based UI, team page, targets page (instructions, failure messages, confirm-before-remove, viewer view).

CI runs the backend suite on a PostgreSQL service. **Not present yet:** Playwright end-to-end tests, Bandit/Semgrep/Trivy gates.
