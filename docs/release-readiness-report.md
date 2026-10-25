# Release-readiness report

Date: 25 October 2026. Scope: the code at `b7f1ddd` plus the small changes in the patch that carries this report.
This is a review of the existing implementation. It is not a penetration test and does not claim the application is secure.
Only tests that were actually executed are reported as passing.

## 1. Verified results

| Check | Result | Where |
|---|---|---|
| Backend tests (934) | all passed | run here on PostgreSQL 16 and by GitHub Actions on PostgreSQL 18 (job `backend`: success on `b7f1ddd`) |
| Frontend unit tests (218) | all passed | run here |
| Browser tests (106) | all passed | run here before the Integrations change was pushed; job `e2e`: success on `b7f1ddd` |
| ruff, mypy, bandit, secret scan | clean | run here; `security` job success on `b7f1ddd` (also pip-audit, npm audit, Semgrep, Trivy) |
| Skipped tests | none here. Four test files skip themselves without `bash/curl/jq`, `openssl`, a git checkout or PostgreSQL. All four are present on the CI runner. | The CI log with skip counts could not be read with the access available, so "none skipped in CI" is inferred from the job setup, not read from a log. |

Reproducing: `pytest` in `backend/` with `SECURESCOPE_TEST_DATABASE_URL` set, `npm test` and `npx playwright test` in `frontend/`.

## 2. Evidence for the eight reported claims

| Claim | Direct automated coverage | Attack realistic? | Asserts the outcome? | Notes |
|---|---|---|---|---|
| 1 Cross-customer access | `test_cross_customer.py`, `test_route_coverage.py` | Yes: a second signed-in customer, real routes, real ids | Yes: status, no echo of secrets, and the owner's data unchanged afterwards | A new route with an id fails the guard until it is added. |
| 2 Agency roles | `test_agency_roles.py` | Yes | Yes, compared with the permission matrix; a deliberate break was caught | No per-client permissions exist (see P2-3). |
| 3 API tokens | `test_token_scope.py`, `test_integrations.py` | Yes | Yes | |
| 4 Scheduled scans | `test_schedule_authorisation.py`, `test_schedules.py` | Yes, the cron path itself | Yes: no scan is created | |
| 5 Webhooks | `test_webhooks.py`, `test_ssrf_matrix.py` | Yes for addresses. Delivery tests replace the network with a fake transport, so what the tests prove is the address the code decides to connect to (the checked IP, with the host name as TLS name), not a real socket. | Yes | A real-socket delivery test is not in the suite (P3-2). |
| 6 SSRF and rebinding | `test_fetcher.py`, `test_target.py`, `test_ssrf_matrix.py` | Yes: a local server, redirects, a name that changes answer between hops | Yes | |
| 7 Account deletion | `test_deletion_sweep.py`, `test_account_deletion_data.py` | Yes | Yes, read from the schema, so new tables are covered | Backups and external services are outside what a test can show (section 6). |
| 8 Subscriptions | `test_subscription_invariants.py`, `test_subscriptions.py` | Rules only: no provider is connected | Yes | Duplicate and out-of-order provider events cannot be tested until a provider exists (P1-1). |

New in this patch: `test_authentication_sweep.py` checks that every API route refuses a visitor except 15 written-out public routes; the sweep found exactly those 15.

## 3. Security controls examined

- Object-level authorisation on every route that takes an id (section 2, claim 1), including exports, share links, members, invitations, sessions and webhook deliveries.
- One outbound path for user-supplied addresses: validate every resolved address, connect to the checked address, keep the host name only for TLS, no redirect following for webhooks, same-origin redirects only for scans, proxy environment variables ignored, response size, request count, time and redirect limits. Covers the scanner, TLS probe, ownership file check, scheduled scans, webhooks and Slack.
- Slack addresses must match one host and path shape.
- Report formats: CSV neutralises formula starts; the HTML report is served with a restrictive content-security policy; downloads are `attachment` with `nosniff`; PDF download links are signed, bound to person, workspace and report, and expire.
- Audit rows hold ids and event names, no emails or IP addresses.

## 4. Confirmed defects

None that exposed another customer's data. Defects found and fixed in this review or the one before it:

- The agency "assign a site to a client" attack in the cross-customer test used a path that does not exist, so it tested nothing. Fixed; the route is now attacked for real and refused.
- The Slack address check used `$`, which accepts a trailing newline. Fixed (`\Z`). The address was already stripped, so this was hardening, not an exploitable hole.
- The private-address test switch (`SECURESCOPE_ALLOW_PRIVATE_TARGETS`) could be combined with a production setup. The server now refuses to start with it when cookies are secure or the public address is https. (P2, fixed.)

## 5. Findings still open

### P1 — serious, before taking money or an external pilot
- **P1-1 Payment events (Phase 4).** No provider is connected, so ordering and duplicate handling cannot be proven. Required when Paddle goes in: verify the signature before anything else; apply an event only if `record_event` returns true (already idempotent); ignore an event older than the stored state (needs the provider's event time, not yet stored); recalculate the plan in one transaction; test replayed, reordered and concurrent events.
- **P1-2 Account deletion with a live subscription.** Deleting the account does not cancel a paid subscription. Needed before any paid plan is sold: cancel at the provider first, or refuse deletion while a subscription is active.
- **P1-3 Legal and data transfer.** The server runs in the US and the legal text has not had a lawyer's review; the transfer mechanism and the German small-business/VAT position are open (you deferred these). They matter before real customers in the EU.
- **P1-4 Mail delivery on the live site.** Registration needs an email that actually arrives. The live sending domain (SPF, DKIM, a real inbox) has not been checked by a real registration. Try it with a second address before any pilot user is invited. (I did not create an account on the live site.)

### P2 — important
- **P2-1 Backups.** Neon's free plan restores only a short window. Scheduled off-site backups are not set up. Deleted accounts also remain in provider backups until those expire; the privacy text should say so.
- **P2-2 Single-instance assumptions.** Rate limits and the running-scan list live in the process. Fine for one instance; with two, every limit doubles and a restart loses scans in progress (they are marked failed on start). A cold start on free hosting also delays the first request.
- **P2-3 Per-client permissions.** Roles apply to the whole workspace. Agencies cannot give a person access to one client only.
- **P2-4 Per-rule tests.** Each rule has a test somewhere, but not a positive, a negative and an edge-case test per rule. Four TLS certificate rules are covered together, not one by one. (Already in the plan.)
- **P2-5 No full browser journey.** The browser tests stub the API for most screens. Registration, email link, site verification, first scan and report are each tested on the backend, but not in one real-browser run.
- **P2-6 Edge protection.** The Cloudflare rate-limit rule is not set; app-level limits are the only layer.
- **P2-7 Operator plan versus subscription.** A bought plan lower than one the operator assigned by hand replaces it while the subscription lasts. Decide the rule before the first subscription.

### P3 — can wait
- P3-1 Schedules belong to the workspace, not the person who created them; they keep running if that person leaves. This is reasonable, but say so in the help text.
- P3-2 A real-socket webhook delivery test (a local TLS receiver).
- P3-3 Read skip counts from the CI log once the log is accessible.

## 6. Production configuration that still needs checking (not visible from the code)
- Render environment: mail provider key and sender, `SECURESCOPE_CRON_SECRET`, `SECURESCOPE_WEBHOOK_SIGNING_KEY`, operator email, `SECURESCOPE_ALLOW_PRIVATE_TARGETS` unset, cookies secure, API docs off (`/api/docs` returns 404).
- Neon: PostgreSQL 18, restore window, connection limits.
- Cloudflare: the cron trigger registered, the rate-limit rule, DNS hardening.
- A real alert email, webhook and Slack message received once; the GitHub Action run once with a new token.

## 7. Customer journey
Registration, email link, site verification (DNS record or file), first scan, findings with fixes, reports in four formats, alerts, plan limits, account settings and deletion are all built and each is tested. Blockers for a new user without help: P1-4 (mail must arrive), the first-request delay after the free host sleeps, and the DNS wait after publishing a record (the page explains it).

## 8. Before an external pilot
Do P1-4 and P1-3 (or knowingly accept them for a small invited group with the "development stage" notice), take a backup (P2-1), and check section 6. Payments (P1-1, P1-2) are needed only when paid plans open.

## 9. What this report does not show
It does not show that the application has no vulnerabilities, that production matches the repository, or how the deployment behaves under load. No load tests have been run.
