# Security audit summary

Date: 25 Oct 2026. Details: [checklist](security-audit-checklist.md), [findings](security-findings.md), [remediation plan](security-remediation-plan.md), [test evidence](security-test-evidence.md).

## Result

68 checks after the closure review: **54 PASS, 6 PARTIAL, 0 FAIL, 2 NOT VERIFIED, 6 NOT APPLICABLE.** No P0 or P1 defect was demonstrated. Fixed: the CORS guard (now exact origins only) and the placeholder database password guard (now case-insensitive), plus a P3 where validation errors echoed the rejected input. See the closure section in the checklist. Everything else that is open needs a decision or action from the owner.

## What was reviewed

Authentication, sessions and cookies, authorisation and roles, tenant isolation on every id-taking route, API tokens, scheduled jobs, SSRF and webhook destinations, account deletion and export, subscription entitlements, configuration handling, logging, input and output handling, security headers and CORS, the built frontend bundle, dependency audits, secret scanning of files and history, CI configuration, and mutation checks on four controls.

## What was not reviewed

- The production host, Neon database roles and settings, Cloudflare configuration, GitHub repository settings (branch protection), and mail-provider behaviour.
- A live penetration test, fuzzing, load testing and real DNS-rebinding against live resolvers.
- Third-party services' own logs.
- Paddle billing and inbound payment webhooks, which do not exist yet.

## Unresolved risks

1. Account deletion does not cancel a live paid subscription (before paid launch).
2. Payment event ordering and duplicates are not handled yet (before paid launch).
3. Migrations run under the runtime database role.
4. Rate-limit counters are in memory and reset on restart.
5. Backups are taken by hand only (restore proven on 25 Oct); no schedule.
6. Branch protection and secret-scanning settings are unconfirmed.

## Readiness, with evidence

- **Local development: ready. Owned or authorised sites: ready with conditions. Controlled pilot with free plans: ready with conditions** (restore test, edge rate limit, branch protection check, production settings checked against the stricter startup guards).
- Earlier statement kept for reference: Isolation, authentication, scanner safety and deletion are covered by tests that were shown to fail when the controls are weakened, and the dependency and secret audits are clean.
- **Public commercial launch: not ready.** Items 1 and 2 above, a tested restore, and the edge rate limit should be done first.

This audit does not show the application is completely secure and it is not a penetration test.
