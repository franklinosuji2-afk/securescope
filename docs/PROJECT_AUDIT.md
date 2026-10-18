# Project audit

Date: 2026-10-18. Scope: the repository as it stood at the start of Phase 1 (SecureScope v0.1).

## What existed (v0.1)

| Area | State |
|---|---|
| Frontend | React 19 + TypeScript (strict) + Vite, hand-written CSS, hash routing. Overview / Findings / Scan History. Vitest + Testing Library (8 tests). |
| Backend | FastAPI, anonymous API (no authentication, no organizations). 5 endpoints. |
| Scanner | DNS-pinned `httpx` fetcher, same-site-only redirects, size/time/request caps; passive checks for HTTPS, security headers, disclosure headers, cookie flags, directory-index signature; heuristic score. |
| Storage | SQLite with hand-rolled migrations. |
| Tests | 110 backend tests (target validation, SSRF/private IP rejection, redirects, checks, scoring, API, reports) using a local mock target; no internet needed. |
| Containers | Dockerfiles, Compose with SQLite volume. |
| CI | GitHub Actions: ruff, mypy, pytest, frontend lint/typecheck/test/build, docker build. |

## What works

SSRF-aware target validation and connection pinning, passive checks, report export (HTML/Markdown/JSON, escaped), retention cleanup, rate limiting (in memory), non-root containers.

## Gaps against the product specification

No users, authentication, organizations, roles, tenant isolation, audit events, target registration, **domain ownership verification**, scan schedules, finding lifecycle/fingerprints, Celery/Redis jobs, OWASP ZAP integration, PDF reports, Tailwind/shadcn UI, Playwright tests, Bandit/Semgrep/Trivy in CI, metrics. Authorization is a checkbox only, which is not proof of ownership.

## Weaknesses found

- Anonymous access: anyone who can reach the API can list every scan. Fine for single-user local use; unacceptable for a hosted product.
- Rate limiter is in-memory and per process.
- SQLite is not a production database.
- Scans run as in-process asyncio tasks, so they die with the process (marked failed on restart).
- Source layout differed from the target layout.

## Changes made in Phase 1

Restructured into the target layout (`core`, `security`, `scanner`, `reporting`, `schemas`, `models`, `repositories`, `database`, `middleware`), API moved to `/api/v1`, readiness endpoint added, SQLAlchemy 2 + Alembic + PostgreSQL replace SQLite, Compose runs Postgres. All 110 original tests still pass, plus 2 new ones.

## Verified in Phase 1

- 112 backend tests pass on SQLite and on a real PostgreSQL 16 server through the real Alembic migration.
- Clean install from pinned `requirements.txt` in a fresh virtualenv; migration CLI applied to Postgres; `/api/v1/ready`, `/api/v1/health` respond; a request to `169.254.169.254` is rejected.
- Frontend: lint, typecheck, 8 tests, production build pass.

## Not verified in Phase 1

Docker image builds and `docker compose up` (Docker is unavailable in the authoring environment; the Compose file only passes `docker compose config`).
