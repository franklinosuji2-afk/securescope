# Architecture (as implemented, v0.2)

```
Browser ──► nginx (frontend, :8080) ──/api/──► FastAPI (backend, :8000) ──► PostgreSQL (internal only)
                                                   │
                                                   └─ in-process asyncio scan tasks ──► target sites (via SSRF-guarded fetcher)
```

## Backend layout (`backend/app`)

| Package | Responsibility |
|---|---|
| `main.py` | App factory, middleware, lifespan, `/api/v1` router |
| `core/` | Settings (`SECURESCOPE_*`), structured JSON logging |
| `security/` | Target URL parsing, DNS resolution and public-address validation (SSRF defence) |
| `scanner/` | DNS-pinned fetcher, passive checks (pure functions), scoring, scan runner |
| `schemas/` | Pydantic request/response models |
| `models/`, `database/`, `repositories/` | SQLAlchemy models, engine/session, repository layer; Alembic in `backend/alembic` |
| `reporting/` | JSON, Markdown and HTML (escaped) reports |
| `middleware/` | Sliding-window rate limiter |
| `tests/` | 112 tests; local mock target, no internet |

## Data

PostgreSQL via SQLAlchemy 2. Schema is created only by Alembic migrations (`python -m app.database.migrate`, run by the backend container before it starts serving). Tests use SQLite by default; set `SECURESCOPE_TEST_DATABASE_URL` to run them on PostgreSQL. SQLite is not supported in production.

## Not yet present

Authentication, organizations, targets, ownership verification, job queue, ZAP, schedules, audit log. See `IMPLEMENTATION_PLAN.md`. Scans currently run as in-process tasks and are not durable across restarts.
