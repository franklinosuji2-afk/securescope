# Threat model

**Scope:** the self-hosted v0.1 MVP. Public multi-tenant hosting is out of scope until the roadmap items are done.

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
| **Unauthenticated access to history** | Designed for single-user local use | **No authentication in v0.1 – do not expose publicly** |

## Not covered
Authentication, tenancy, audit logging, abuse monitoring, legal review (required before SaaS).
