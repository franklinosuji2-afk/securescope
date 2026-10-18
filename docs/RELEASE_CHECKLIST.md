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
