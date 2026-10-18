# Known limitations

- Passive checks of **one page** (the final response after same-site redirects). Other paths, authenticated areas and APIs are not examined.
- Cookie checks only see cookies set on that response.
- Header presence is checked; CSP/HSTS *quality* is only lightly assessed.
- The directory-index check is a conservative signature and can miss or (rarely) misfire.
- No TLS/certificate analysis, no software-version vulnerability matching, no active testing (by design).
- The score is a heuristic, not comparable to other tools. A high score does not mean a site is secure.
- DNS pinning mitigates rebinding, but production should still use an egress proxy.
- Rate limits are in-memory and per process. Single node. No authentication or multi-user support (planned: Phase 2).
- Docker images were authored and the Compose file validated, but image builds were not executed in the authoring environment. Run `docker compose up --build` and the release checklist before relying on them.
