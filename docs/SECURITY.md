# Security design (as implemented, v0.4)

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

| Permission                                                        | OWNER | ADMIN                  | SECURITY_ANALYST | MEMBER | VIEWER |
| ----------------------------------------------------------------- | ----- | ---------------------- | ---------------- | ------ | ------ |
| Read organization, scans, findings                                | yes   | yes                    | yes              | yes    | yes    |
| Export reports                                                    | yes   | yes                    | yes              | yes    | yes    |
| Start scans                                                       | yes   | yes                    | yes              | yes    | no     |
| View targets                                                      | yes   | yes                    | yes              | yes    | yes    |
| Add, verify, regenerate, remove targets                           | yes   | yes                    | yes              | no     | no     |
| Change a finding's status (accepted risk, false positive, reopen) | yes   | yes                    | yes              | no     | no     |
| Cancel or retry scans                                             | yes   | yes                    | yes              | yes    | no     |
| Read the audit log                                                | yes   | yes                    | no               | no     | no     |
| Read clients and the dashboard (Agency plan)                      | yes   | yes                    | yes              | yes    | no     |
| Create, edit, delete clients; assign sites; set agency name       | yes   | yes                    | no               | no     | no     |
| Create and revoke report share links (Agency plan)                | yes   | yes                    | yes              | no     | no     |
| Add / change / remove members                                     | yes   | yes (below ADMIN only) | no               | no     | no     |

Admins cannot grant OWNER or ADMIN, cannot change or remove admins or owners, and cannot promote themselves. An organization always keeps at least one owner. Any member can leave. The matrix lives in `app/security/permissions.py`; the frontend mirrors it for display only.

## Domain ownership (targets)

A scan may only run against a host that the active organization has registered **and verified**. A target is a canonical, lower-case, punycode host name (no port, path or credentials). IP literals, single-label names and internal suffixes are rejected at registration because ownership of those cannot be proven with DNS.

Each target has a random 128-bit challenge that expires after 7 days (expired challenges cannot be used; a new one can be issued, which invalidates the old value; the value is erased once the domain is verified, when it is removed, and after it expires; a check that finishes after the challenge was replaced or removed cannot verify the domain). Two methods:

- **DNS TXT** at `_securescope-challenge.<host>` with value `securescope-verification=<token>` (exact match; other labels and the apex do not count).
- **HTTP file** at `/.well-known/securescope-verification.txt` containing the same value. Fetched with the SSRF-hardened scanner fetcher (public addresses only, DNS pinning, same-site redirects). The response must be HTTP 200, at most 512 bytes, and served from exactly the registered host (a redirect to `www.` does not count).

Verification is exact-host: `example.com` does not authorise `www.example.com` or subdomains; register each one. Verification is per organization; another organization's verification gives you nothing. Verification attempts are rate limited per target. A failed check never marks a target verified, and the reason is shown to the user. Deleting a target immediately blocks further scans of it. Tests: `app/tests/test_targets.py`.

## Audit log

`audit_events` records registration, logins (success and failure, without the email), logout, session refresh, password reset and email verification, organization creation, member add/role change/removal, target creation/verification/failed verification/challenge regeneration/removal, scan creation, cancellation and retry, report export and finding status changes, each with actor, resource and request id. Owners and admins can read it (`GET /audit-events`, the **Audit log** page); every other role gets 403, and one organization never sees another's events (tests: `app/tests/test_audit_log.py`).

## PDF reports

Reports are made on the server from an HTML template (WeasyPrint). Every scan value goes into the template as data and is escaped, so evidence a remote server sent can never become markup, and the renderer is not allowed to fetch anything: no remote images, stylesheets or fonts, whatever the text contains (tests: `app/tests/test_pdf_report.py`). A report is built once per finished scan, one at a time, off the event loop, and only for a scan that completed (a failed or cancelled scan has no report).

Reports are stored privately in the database with a SHA-256 checksum that is verified on every read. They are never served from a fixed address. `GET /scans/{id}/report/pdf` returns a link that expires after 5 minutes (`SECURESCOPE_DOWNLOAD_URL_TTL_SECONDS`), signed for that person, that organization and that report; the download route also needs the signed-in session, membership of the organization and ownership of the scan, and anything else looks like a missing report. A link is a bearer token only together with the session, so a copied link is useless to someone else. It is not single-use: it can be opened again until it expires. Without `SECURESCOPE_DOWNLOAD_SIGNING_KEY` the key is random per start, so links stop working after a restart and people ask for a new one.

## Email confirmation

An account must confirm its email address before it can use targets, scans, results or reports. The server enforces this (`SECURESCOPE_REQUIRE_VERIFIED_EMAIL`, on by default); the app only explains it. Google and GitHub sign-in count as confirmed because the provider has verified the address.

## Scanner safety

See `THREAT_MODEL.md`: SSRF controls, DNS pinning, redirect validation and limits are unchanged from v0.1.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository.

## Passive checks added in Stage 2

- **TLS certificate** (`SS-TLS-CERT-001..005`): one verified connection using Python's default context (verification is never disabled). Findings: expires within 30 days (high at 14 or fewer), expired, host name mismatch, untrusted chain, not yet valid.
- **Fixed-path probes** (`SS-EXPOSE-GIT-001`, `SS-EXPOSE-ENV-001`, `SS-DISC-SEC-001`): constants in `scanner/checks.py`, never user input. They reuse the SSRF-validated, IP-pinned fetch path, do not follow redirects, read at most 4 KB, and store no file content.
- Checks that could not run are listed under `metadata.checks_skipped` and shown as "Not checked".

## Share links

A share link is a random 256-bit token, stored only as a SHA-256 hash and shown once. It exposes one scan's PDF report and nothing else (never client notes). Links expire (default 14 days) and can be revoked. Unknown, revoked, expired and malformed tokens all return the same 404. Responses are `no-store`, `noindex` and `no-referrer`, the token lives in the URL fragment in the app, and the public routes are rate limited.

## Automated security checks

Run on every push by `.github/workflows/ci.yml`, and locally with the same commands:

- **Secrets:** `python scripts/scan_secrets.py --history` looks for common token shapes (cloud keys, GitHub and Slack
  tokens, private keys, database URLs with passwords, SecureScope tokens) in tracked files and in every commit, and
  fails on forbidden file types (`.env`, keys, dumps). It prints where, never the value. `.gitignore` also keeps
  patches, backups and `.env.*` files out of git.
- **Dependencies:** `pip-audit` (Python, pinned requirements) and `npm audit --audit-level=high` (frontend).
- **Static analysis:** Bandit, Semgrep (Python, OWASP Top Ten, TypeScript) and Trivy (vulnerabilities, secrets,
  Dockerfile and Compose).
- **Customer isolation:** `test_tenancy.py` and `test_cross_customer.py`. The second one calls every route that takes
  an id (targets, scans, reports in every format including the PDF and its signed download, shares, findings,
  schedules, webhooks, API tokens, badges) as a different customer and requires a refusal, then checks the owner's
  data is unchanged. It also checks that a CI token cannot cross workspaces or act as a login.
- **Scanner network limits:** `test_target.py`, `test_ssrf_matrix.py` and `test_fetcher.py` cover private, loopback,
  link-local, NAT64, 6to4, IPv4-mapped and reserved addresses, numeric host forms, URL tricks, off-origin and
  downgrade redirects, DNS rebinding between hops and the pinned connection.

## Latest audit

A 68-point audit was done on 25 Oct 2026: see [security-audit-summary.md](security-audit-summary.md), with the checklist, findings, remediation plan and test evidence next to it.
