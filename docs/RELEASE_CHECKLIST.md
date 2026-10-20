# Release checklist

- [ ] CI green (backend ruff/mypy/pytest, frontend lint/typecheck/test/build, docker build)
- [ ] `docker compose up --build` from a clean clone; health checks become healthy
- [ ] Scan an authorized public site; findings, history and all three exports work
- [ ] Private/loopback targets are rejected (`http://127.0.0.1`, `http://169.254.169.254`)
- [ ] `SECURESCOPE_ALLOW_PRIVATE_TARGETS` is not set
- [ ] Dependency audit (`pip-audit`, `npm audit`) reviewed
- [ ] Licence chosen; name/trademark search done
- [ ] README implemented-vs-roadmap table still accurate
- [ ] **Before any public hosting:** ownership verification, authentication, tenant isolation, edge rate limits, abuse monitoring, audit logs, privacy notice, legal review
- [ ] Analytics: `SECURESCOPE_ADMIN_EMAIL` set on the API host, that account's email confirmed, `SECURESCOPE_ANALYTICS_SALT` set to a long random value; open a public page in a private window and confirm it appears under Analytics
- [ ] Privacy notice mentions the visit statistics and the retention (`SECURESCOPE_ANALYTICS_RETENTION_DAYS`) matches it
- [ ] Platform Health opens for the operator account and shows the database as reachable; if `/metrics` is wanted, `SECURESCOPE_METRICS_TOKEN` is set on the API host and `curl -H "Authorization: Bearer ..." .../metrics` answers 200 (and 401 without the header)

- [ ] Renew `frontend/public/.well-known/security.txt` before its `Expires` date (2027-07-01); RFC 9116 allows at most one year. A unit test fails once the date has passed.
- [ ] Confirm `security@getsecurescope.com` actually receives mail (send a test message).

- [ ] Before a release that adds a migration: take a backup (`scripts/backup-db.ps1`) and confirm the file verifies.
- [ ] Uptime monitor on `/api/v1/ready` is active and alerts reach a mailbox you read (`docs/OPERATIONS.md` section 1).
