# Security findings

Audit of 25 Oct 2026. Findings are ordered by priority and each names its evidence. **No P0 or P1 defect was demonstrated.** Nothing here claims the application is completely secure; see [security-audit-summary.md](security-audit-summary.md) for what was not reviewed.

## Demonstrated defects

None rated FAIL. No cross-customer access, authentication bypass, injection, SSRF or secret exposure was found.

## Confirmed gaps, fixed in this audit

### F1 (P3, hardening): CORS accepted a wildcard together with credentials
- **Evidence:** `core/config.py` took `cors_origins` as a plain list and `main.py` enables credentials. A value of `*` would have started without complaint; with credentials that lets any website read a signed-in visitor's data. The request-origin check for unsafe methods compares exact strings, so it would not have caught reads.
- **Not exploitable today:** the deployed list contains exact origins (the default is two localhost addresses).
- **Fix:** start-up refuses `*`, wildcard hosts, `null` and empty entries. Tests: `test_config_guards.py`.
- **Owner check before deploying:** if `SECURESCOPE_CORS_ORIGINS` on the host contains a wildcard, the service will now refuse to start. It should list exact origins only.

### F2 (P3, hardening): placeholder database password accepted
- **Evidence:** the default `database_url` carries the password `change-me`. A production start-up with the variable missing would have tried that URL rather than refusing.
- **Fix:** an https deployment (`PUBLIC_BASE_URL` starting with https) is refused if the database URL still contains `change-me`. Local development and tests are unaffected.

## Open items needing the owner (not changed)

| ID | Priority | Item | Why not changed |
|---|---|---|---|
| O1 | P1 before paid launch | Deleting an account does not cancel a live paid subscription. No paid plan exists yet. | Needs the billing provider design (Paddle) |
| O2 | P1 before paid launch | Payment event ordering and duplicate handling does not exist yet (release-readiness P1-1). | No inbound webhook exists to protect yet |
| O3 | P2 | Migrations run at container start under the application's database role, so the runtime role can alter the schema. Use a separate migration role. | Hosting change, owner approval |
| O4 | P2 | Rate-limit counters are in memory (reset on restart, not shared across instances). Add the Cloudflare edge rule. | Edge configuration is outside the repository |
| O5 | P2 | Backup and restore scripts have not been run on the owner's PC against the real database. | Needs the owner's machine and database |
| O6 | P2 | Branch protection, required reviews and secret-scanning settings could not be read (403). | Needs the owner to check GitHub settings |
| O7 | P3 | No idle timeout and no `__Host-` prefix on the session cookie; first-party GitHub Actions are pinned to major tags rather than commit hashes. | Hardening only |
| O8 | Owner | Local secret files in the owner's Downloads folder (noted earlier) should be deleted and anything ever shared in a chat rotated. | Outside the repository; rotation needs approval |

## Things that held up

- Cross-customer isolation, agency roles, API-token limits, scheduled-scan authorisation and account deletion, each tested end to end (route-coverage test fails when a new id-taking route is not covered).
- SSRF, DNS answers pointing at private or metadata addresses, webhook URL tricks.
- Argon2id passwords, hashed opaque tokens, HttpOnly session cookie, CSRF token on every unsafe request, session revocation on logout, reset and password change.
- No raw SQL, no unsafe deserialisation, no command execution, no file upload, no source maps, no secret-shaped strings in the bundle.
- pip-audit and npm audit report no known vulnerabilities (on the audit date).
- Mutation checks showed the tests detect weakened CSRF, address-validation and session-revocation controls.
