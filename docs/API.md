# API (v0.4)

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
| GET | `/targets`, `/targets/{id}` | target:read | Scoped to the active organization |
| POST | `/targets` | target:manage | `{"hostname"}`; 201 with the challenge; 400 invalid host; 409 duplicate |
| DELETE | `/targets/{id}` | target:manage | 204 |
| POST | `/targets/{id}/challenge` | target:manage | New token and expiry |
| POST | `/targets/{id}/verify` | target:manage | `{"method": "dns_txt"\|"http_file"}`; 200 with the updated target (check `status` and `last_check_error`), 409 if expired, 429 if rate limited |
| POST | `/scans` | scan:create | 202; requires `authorization_confirmed` **and a verified target for the exact host (403 otherwise)** |
| GET | `/scans`, `/scans/{id}` | scan:read | Scoped to the active organization |
| GET | `/scans/{id}/report?format=json\|md\|html` | report:export | Includes confidence and status per finding |
| PATCH | `/findings/{fingerprint}` | finding:triage | `{"status": "open"\|"accepted_risk"\|"false_positive", "note"?}` (note max 500); 204; 404 for unknown or other-organization findings; 422 for `resolved` (system only) |

Errors are `{"detail": "..."}`; validation errors are 422. **Not implemented:** periodic re-verification, schedules, report storage, PDF.

## Findings

Every finding in a scan response carries `fingerprint` (a stable id for that check on that host), `confidence` (`high` for direct observations, `medium` for heuristic signature matches), `status`, `status_note`, `first_seen_at` and `last_seen_at`. Status is kept per organization and host. A finding becomes `resolved` only when a later **completed** scan of the same host no longer reports it; failed scans and scans that stopped at a redirect to another site never resolve anything. A resolved finding that appears again returns to `open`. `accepted_risk` and `false_positive` are analyst decisions and are not changed by scans.
