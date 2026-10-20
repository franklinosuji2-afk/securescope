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
