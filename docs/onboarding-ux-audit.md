# Onboarding and UX audit

Phase 7 of the product-quality brief. Labels: **Verified** (code, tests), **Risk**, **Recommendation**, **Not tested**.

## First-run path (from the code)

Register or sign in with Google/GitHub, confirm the email address, add a site, prove ownership (DNS record or file), run a scan, read the result. The Overview shows a "Get your first result" guide until the first scan has completed: ordered steps, the current one marked, a link for the next action, and a plain statement that results appear only after a real scan has run. Empty states elsewhere say what is missing and what to do (for example "No sites added yet", "Nothing to compare yet").

## Verified

- **Accessibility:** an automated check runs on the main pages in the browser tests (`accessibility.e2e.ts`) and layouts are tested at phone width (`responsive.e2e.ts`).
- **Honest wording:** the guide, empty states and the "Nothing needs action right now. This does not mean your sites are secure." message do not overclaim. The score card carries the "heuristic, not proof" caveat.
- **Verification flow:** `targets.e2e.ts` covers adding a site and verifying it; errors from a failed verification are shown with the reason (`last_check_error`).

## Defect found and fixed

- **The on-screen checklist counted a certificate problem twice.** The "What we checked" list matched findings to checks by id prefix. The HTTPS check used `SS-TLS-`, which also matches certificate findings (`SS-TLS-CERT-`), so one certificate problem marked both "HTTPS" and "TLS certificate" as needing attention and lowered the "n of m checks passed" count, while the exported reports (which use `SS-TLS-0`) said HTTPS passed. The screen now uses the same prefix. Tests: two frontend cases (one fails without the fix) and a backend test that compares the screen's checks, prefixes and "not passed at info" list with the backend's, so they cannot drift apart again.

## Risks and recommendations

| # | Finding | Type |
|---|---|---|
| 1 | Ownership verification is the longest step for a new user (a DNS record needs access to the domain's DNS and may take time to propagate). The page explains both methods; there is no estimate of how long DNS takes or a "check again in a few minutes" prompt. | Recommendation (copy) |
| 2 | Email confirmation is required before verified-owner features. If the confirmation mail does not arrive, the only way forward is "resend" (3 per hour). Live mail delivery has not been checked end to end (release-readiness P1-4). | Risk |
| 3 | Scans run on a free-tier backend that sleeps; the first request after idle can take about a minute. The page shows a loading state but does not say why it is slow. Keep-warm or a paid instance is queued. | Risk (first impression) |
| 4 | Finding detail pages show fixes for several servers; there is no way to say which stack the user runs and see only that fix. | Recommendation |
| 5 | The first-run flow was read from code and tests only. Creating an account on the live site was not done (not permitted), so the real first-run experience, email timing and cold-start behaviour have not been observed. | Not tested |
| 6 | No usability testing with real users has been done. Any statement about ease of use is therefore unmeasured. | Not tested |
