# API (v0.3)

Base path `/api/v1`. Interactive schema at `/api/docs` when the backend is reached directly. Cookie-authenticated; unsafe methods need `X-CSRF-Token`; multi-organization users select one with `X-Organization-Id`.

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | 200 when the database answers, else 503 |
| POST | `/auth/register` | none | Creates user + personal organization (OWNER); starts a session |
| POST | `/auth/login` | none | Generic error on failure; rate limited |
| POST | `/auth/logout` | session | 204 |
| POST | `/auth/refresh` | session | Rotates session and CSRF tokens |
| GET | `/auth/me` | session | User and organizations with roles |
| POST | `/auth/forgot-password` | none | Always 202 |
| POST | `/auth/reset-password` | none | Single-use token; ends all sessions |
| POST | `/auth/verify-email` | none | Single-use token |
| POST / GET | `/organizations` | session | Create / list own |
| GET | `/organizations/{id}` | member | 404 for non-members |
| POST | `/organizations/{id}/members` | OWNER, ADMIN | Add an existing user |
| PATCH / DELETE | `/organizations/{id}/members/{user_id}` | OWNER, ADMIN (members may leave) | |
| POST | `/scans` | scan:create | 202; requires `authorization_confirmed` |
| GET | `/scans`, `/scans/{id}` | scan:read | Scoped to the active organization |
| GET | `/scans/{id}/report?format=json\|md\|html` | report:export | |

Errors are `{"detail": "..."}`; validation errors are 422. **Not implemented:** targets, ownership verification, findings lifecycle endpoints, schedules, report storage, PDF.
