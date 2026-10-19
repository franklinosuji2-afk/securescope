# Known limitations

- Passive checks of **one page** (the final response after same-site redirects). Other paths, authenticated areas and APIs are not examined.
- Cookie checks only see cookies set on that response.
- Header presence is checked; CSP/HSTS _quality_ is only lightly assessed.
- The directory-index check is a conservative signature and can miss or (rarely) misfire.
- No TLS/certificate analysis, no software-version vulnerability matching, no active testing (by design).
- The score is a heuristic, not comparable to other tools. A high score does not mean a site is secure.
- DNS pinning mitigates rebinding, but production should still use an egress proxy.
- Rate limits are in-memory and per process; single node.
- Email goes out only when a provider is configured (`SECURESCOPE_MAIL_PROVIDER=brevo|resend`); with the default `log` mailer, links are only written to the server log. A provider outage is logged and does not fail the request, so the user is not told that an email did not arrive.
- Registration reveals whether an email is already registered (409); mitigated by rate limiting only.
- Domain ownership is verified once and stays verified until the target is deleted; there is no periodic re-verification, so a domain that changes hands stays authorised. Verification is exact-host (no wildcard/subdomain scope), and only domain names are supported (no IP targets).
- Ownership verification: the HTTP-file method was confirmed once end to end on a real domain (2026-10-18, the author's own site, followed by a real scan and report). The DNS TXT method has only been tested with mocked lookups and error mapping, not against a live domain.
- DNS TXT verification trusts the resolver the server is configured with.
- Members can only be added if they already have an account; there are no emailed invitations.
- The audit log is write-only (no API or UI); users cannot list or revoke individual sessions.
- Use the app only via the configured origin (`http://localhost:8080`); other origins are refused for POSTs.
- Docker images were authored and the Compose file validated, but image builds were not executed in the authoring environment. Run `docker compose up --build` and the release checklist before relying on them.
