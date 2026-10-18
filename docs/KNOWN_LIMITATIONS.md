# Known limitations

- Passive checks of **one page** (the final response after same-site redirects). Other paths, authenticated areas and APIs are not examined.
- Cookie checks only see cookies set on that response.
- Header presence is checked; CSP/HSTS *quality* is only lightly assessed.
- The directory-index check is a conservative signature and can miss or (rarely) misfire.
- No TLS/certificate analysis, no software-version vulnerability matching, no active testing (by design).
- The score is a heuristic, not comparable to other tools. A high score does not mean a site is secure.
- DNS pinning mitigates rebinding, but production should still use an egress proxy.
- Rate limits are in-memory and per process; single node.
- Email verification and password reset links are only written to the server log (development mailer). No real email is sent.
- Registration reveals whether an email is already registered (409); mitigated by rate limiting only.
- Scans need only a checkbox, not proof of domain ownership (Phase 3).
- Members can only be added if they already have an account; there are no emailed invitations.
- The audit log is write-only (no API or UI); users cannot list or revoke individual sessions.
- Use the app only via the configured origin (`http://localhost:8080`); other origins are refused for POSTs.
- Docker images were authored and the Compose file validated, but image builds were not executed in the authoring environment. Run `docker compose up --build` and the release checklist before relying on them.
