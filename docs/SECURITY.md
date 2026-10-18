# Security design (as implemented, v0.3)

## Authentication

- Passwords: Argon2id (`argon2-cffi` defaults), minimum 12 characters, maximum 128. Hashes are upgraded transparently on login when parameters change.
- Sessions: opaque random token (256 bits) in a cookie; only its SHA-256 digest is stored. Cookie `ss_session`: `HttpOnly`, `SameSite=Lax`, `Secure` (default; Compose turns it off for local HTTP only), 12 h lifetime (`SECURESCOPE_SESSION_TTL_HOURS`). Nothing is kept in `localStorage`.
- Server-side revocation: logout, refresh (rotation), and password reset (revokes all of the user's sessions).
- Login does not reveal whether an account exists (same error, password hash always verified).
- Rate limits (in memory, per process): 5 failed logins per email and 20 per IP per 15 minutes; 10 registrations and 5 reset requests per IP per hour.
- Email verification and password reset use single-use, expiring tokens (24 h / 1 h), stored hashed. **No real email is sent** – the development mailer writes the link to the server log. Do not rely on either flow for real users until a production mailer exists.

## CSRF and cross-origin

- Every unsafe request that carries a session must send `X-CSRF-Token` equal to the token bound to that session (`ss_csrf` cookie is readable by the SPA for this).
- Unsafe requests with an `Origin` that is not in `SECURESCOPE_CORS_ORIGINS` are rejected with 403 (this also covers login CSRF).
- CORS allows only configured origins, credentials, methods GET/POST/PATCH/DELETE and the headers `Content-Type`, `X-CSRF-Token`, `X-Organization-Id`.
- Browse the app only through the configured origin (default `http://localhost:8080`). `http://127.0.0.1:8080` is a different origin and POSTs will be refused.

## Multi-tenancy

Every scan row carries an `organization_id`. All reads go through repository methods that require it (`get_scan(scan_id, organization_id)`, `list_scans(organization_id)`). The active organization is chosen by the client with `X-Organization-Id` but is **only accepted when the authenticated user is a member**; otherwise 403. Scans or organizations belonging to someone else return 404, the same as a non-existent id. Tests: `app/tests/test_tenancy.py`.

## Roles

| Permission | OWNER | ADMIN | SECURITY_ANALYST | MEMBER | VIEWER |
|---|---|---|---|---|---|
| Read organization, scans, findings | yes | yes | yes | yes | yes |
| Export reports | yes | yes | yes | yes | yes |
| Start scans | yes | yes | yes | yes | no |
| Add / change / remove members | yes | yes (below ADMIN only) | no | no | no |

Admins cannot grant OWNER or ADMIN, cannot change or remove admins or owners, and cannot promote themselves. An organization always keeps at least one owner. Any member can leave. The matrix lives in `app/security/permissions.py`; the frontend mirrors it for display only.

## Audit log

`audit_events` records registration, logins (success and failure, without the email), logout, session refresh, password reset and email verification, organization creation, member add/role change/removal, scan creation and report export, each with actor, resource and request id. There is no API or UI to read it yet.

## Scanner safety

See `THREAT_MODEL.md`: SSRF controls, DNS pinning, redirect validation and limits are unchanged from v0.1.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository.
