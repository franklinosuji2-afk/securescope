# Threat model

**Scope:** the self-hosted v0.3 MVP (accounts and organizations, no ownership verification). Public multi-tenant hosting is out of scope until the roadmap items are done.

## Assets
Host network (internal services), scan records, availability, third-party targets (must not be harmed).

## Threats and mitigations

| Threat | Mitigation | Residual risk |
|---|---|---|
| **SSRF** – scanner pointed at internal services or cloud metadata | http/https only, port allow-list, no credentials in URL, DNS resolved and all addresses must be global; same checks on every redirect | Production should add an egress proxy / network policy |
| **DNS rebinding / TOCTOU** | Connection made to the validated IP (pinning) with original Host/SNI | Same as above |
| **Redirect abuse** | Max redirects; only same-site hops; no HTTPS→HTTP; off-origin reported, not followed | – |
| **Using the tool against third parties** | Authorization acknowledgement, passive requests only (≤6 per scan), per-client and per-target rate limits, no payloads | Acknowledgement is not proof of ownership; **add DNS TXT/HTTP-token verification before public release** |
| **Resource exhaustion** | Timeouts, response byte cap, scan duration cap, concurrency semaphore, rate limits | Limiter is in-memory, per process |
| **Stored XSS via target-controlled data** (headers, cookie names) | React escapes output; HTML report escapes all values; strict CSP on API and UI | – |
| **Secret leakage** | Bodies never stored; cookie values and sensitive evidence redacted | – |
| **Container privilege** | Non-root user, read-only root FS, dropped capabilities, no-new-privileges | Keep base images updated |
| **Supply chain** | Exact-pinned dependencies, CI | Add automated dependency audit |
| **Unauthorised access to scans** | Cookie sessions, CSRF tokens, Origin check, per-organization scoping in the repository layer, 404 for other tenants' ids, server-side RBAC (see SECURITY.md) | Single-process rate limits; no MFA |
| **Credential stuffing / brute force** | Argon2id, per-email and per-IP login limits, generic errors | In-memory limiter resets on restart |
| **Session theft** | HttpOnly + Secure(+SameSite) cookie, server-side revocation, tokens stored hashed | Requires HTTPS in production (`cookie_secure`) |
| **Scanning sites the user does not own** | Checkbox only | **Ownership verification is Phase 3; do not expose publicly before it exists** |

## Not covered
Authentication, tenancy, audit logging, abuse monitoring, legal review (required before SaaS).
