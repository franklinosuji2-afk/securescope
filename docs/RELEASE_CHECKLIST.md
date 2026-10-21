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
- [ ] Confirm `hello@`, `support@`, `privacy@` and `security@getsecurescope.com` all receive mail (send a test message to each; see `docs/EMAIL_SETUP.md`).

- [ ] Before a release that adds a migration: take a backup (`scripts/backup-db.ps1`) and confirm the file verifies.
- [ ] Uptime monitor on `/api/v1/ready` is active and alerts reach a mailbox you read (`docs/OPERATIONS.md` section 1).
- [ ] If Google or GitHub sign-in is enabled: the redirect URIs match `docs/OAUTH_SETUP.md`, the Google consent screen is **In production**, and both a new and an existing account can sign in.
- [ ] PDF reports: the Docker image builds, and downloading a PDF for a finished scan works on the live site (open it; check the logo, the findings and the page breaks). Try the PDF button as a Viewer too.
- [ ] Account page: change the password of a test account (other devices are signed out), then delete a throwaway account and confirm it can no longer sign in.
- [ ] A signed-in account whose email is not confirmed sees the "Confirm your email address" page, not the dashboard.
- [ ] After a release, a tab left open shows "A new version of SecureScope is available" within 15 minutes (or on returning to the tab).
- [ ] If invitations are used: invite a second address as Viewer, accept it in a private window, and confirm it is read-only (`docs/INVITATIONS.md`).
