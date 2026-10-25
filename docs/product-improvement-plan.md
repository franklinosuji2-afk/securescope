# Product improvement plan

Date: 25 Oct 2026. Final document of the product-quality review (phases 0 to 11, 16 patches). It states what was verified, what to do next and in which order, and what should **not** be built yet. Every statement points to the audit that holds the evidence. Nothing here claims the product is ready for a commercial launch; passing tests show that the code does what the tests say, not that the product is safe to sell.

Labels: **Verified** (read in the code, or a test that was run), **Owner-reported** (stated by the owner, not checkable from here), **Not tested**, **Recommendation**.

## 1. Executive summary

SecureScope is a passive website security checker with accounts, ownership verification, scheduled monitoring, reports, teams, an agency workspace, alerts and a CI integration. It is **in a good state for a controlled pilot with free plans** and **not ready to take payments or to be offered publicly as a commercial service**.

- **Strong:** isolation between customers (every id route is attacked as another customer, and a guard test fails for any new route), outbound-request safety, honest wording (nothing in the product, reports or legal text says a clean result means a site is secure), bounded data growth, and a restore that has been rehearsed.
- **Weak, in order of weight:** billing is only groundwork (nothing is sold, and several provider-side rules do not exist yet); rate limits and the running-scan list live in one process's memory; backups are manual; the first-run journey and live email delivery have never been observed end to end by a real new user; there has been no load test.
- **What the review changed:** 12 defects or weaknesses were found and fixed, each with a test (section 2); the listed findings that were not fixed are written down with their reasons.
- **No product-defining decision is open for engineering.** The open decisions are the owner's (section 11).

## 2. Verified current state

**Code and tests (25 Oct 2026, commit `5592776`):** 1028 backend tests and 230 frontend tests pass locally; GitHub Actions is green on all five jobs (frontend, security with pip-audit, npm audit, Semgrep and Trivy, backend on PostgreSQL 18, Playwright browser tests, docker). Ruff, mypy (180 files), bandit and the secret scan are clean. The security audit (68 checks) stands at 54 PASS, 6 PARTIAL, 0 FAIL, 2 NOT VERIFIED, 6 N/A (`security-audit-summary.md`).

**Defects found and fixed during the review (each with a failing-then-passing test):**

| # | Defect | Audit |
|---|---|---|
| 1 | Scan history ran one extra query per scan | `product-improvement-audit.md` |
| 2 | Scan comparison called a check that did not run "resolved" or "new" | `monitoring-and-alerting-audit.md` |
| 3 | Images listed only in `srcset` were not checked for mixed content | `scanner-accuracy-audit.md` |
| 4 | CI results ignored triage (false positives could fail a pipeline) | `developer-experience-audit.md` |
| 5 | The setup checklist counted one certificate problem twice | `onboarding-ux-audit.md` |
| 6 | The client PDF left out false positives without saying so | `reporting-audit.md` |
| 7 | Startup validation of CORS origins and of the placeholder database password was too loose (now exact origins, case-insensitive check) | `security-audit-summary.md` |
| 8 | Request-validation errors are now reduced to location, message and type, so submitted values are never echoed | `security-audit-summary.md` |
| 9 | The history clean-up used the stored plan, so paying customers would have been treated as Free | `subscription-readiness-audit.md` |
| 10 | One failed step stopped all retention until a restart | `operational-readiness-audit.md` |
| 11 | The agency dashboard read every scan of every site to use the newest | `performance-review.md` |
| 12 | Every visitor downloaded the whole app (498 kB; now 371 kB for the first visit) | `performance-review.md` |

**Also done:** the public home page gained support and security-reporting links, an audience statement, a monitoring explanation and a softer ownership claim, with a test that blocks overclaiming phrases (`marketing-and-documentation-audit.md`); an operator-only activation funnel counts existing records without any new tracking (`analytics-and-feedback-audit.md`).

**Operations (Owner-reported and checked where noted):** a backup and restore of the production database passed on 25 Oct (schema 0018, 28 tables; logged in `OPERATIONS.md`). Cloudflare's leaked-credential check is on; a GitHub ruleset blocks force pushes and deletion on `main` (Owner-reported, the API refused the check). The database password is not the placeholder (Owner-reported; the startup guard also refuses it).

**Not tested anywhere:** behaviour under load; the live first-run journey with a real new account; a real alert email, webhook and Slack message on the live site; the GitHub Action from a real workflow with a real token; the agency screens on a paid plan; the PDF by eye (it is checked by extracted text); accuracy of the scanner against real third-party sites (no accuracy percentage is claimed anywhere).

## 3. Top ten evidence-based improvements

| # | Improvement | Priority | Effort | Evidence |
|---|---|---|---|---|
| 1 | **Observe the real first-run journey and live mail delivery** (new account, confirmation email, add and verify a site, first scan) and fix what it shows | P1 | Small (owner time) plus unknown fixes | Onboarding audit risks 2, 3 and 5; release-readiness P1-4. Nobody has seen it. |
| 2 | **Scheduled backups** with a read-only database role | P1 for the pilot | Small | Operational audit: backups are by hand, the free restore window is short; security item 60 PARTIAL. |
| 3 | **Verify fix** and "confirmed resolved" separated from "no longer detected" | P1 | Medium | Product audit section 3; reporting audit. Today a fix cannot be confirmed without a full new scan. |
| 4 | **Overdue-schedule warning and failed-mail alert** | P1 for the pilot | Small | Monitoring audit risks 1, 2 and 5: if the cron stops, scans stop silently; failed mail alerts nobody. |
| 5 | **Billing foundation before Paddle**: signed webhook receiver, record-and-apply in one transaction, ordering of late events, trial and paused mapping, cancel at the provider before account deletion | P1 before any payment | Large | Subscription audit "Before Paddle", seven items; security checklist item 12. |
| 6 | **Shared rate limits and a load test** (or a paid edge plan) | P1 before public launch | Medium | Security items 34 and 53 PARTIAL; counters reset on restart and are per process. |
| 7 | **Separate database roles** for migrations and runtime | P2 (P1 before public launch) | Medium | Security items 27 and 59; operational audit risk 5. |
| 8 | **Portfolio usability**: filter and sort on Targets, next scheduled scan on Overview, tie wording | P2 | Small | Dashboard audit gaps 1 to 5. |
| 9 | **Agency**: client-level report, then a premium PDF cover | P2 | Medium | Agency audit gap 1; reporting audit risk 1. |
| 10 | **Public documentation and addresses**: a reviewed public docs page, search-friendly addresses, `Retry-After` on 429, changelog and tagged releases | P2/P3 | Medium | Marketing audit gaps 1 and 2; developer-experience audit risks 2 to 5. |

## 4. Everything else, by priority

| P | Item | Source |
|---|---|---|
| P0 | **None open.** No result that overstates security was found. | All audits |
| P1 | Items 1 to 6 above | |
| P1 | Cancel at the provider on account deletion (part of item 5, listed because it is a launch blocker) | Subscription audit |
| P2 | Items 7 to 9; webhook retry queue (deliveries retry on 5xx and 429 but a lost run is not re-sent) | Monitoring audit |
| P2 | Privacy notice: say what Cloudflare's leaked-credential check does | Marketing audit (needs owner and lawyer) |
| P2 | Pin the six certificate-rule severities in a test; extend the two "thin" rules (SS-DNS-SPF-003, SS-MIX-002) | Scanner accuracy audit |
| P3 | Scanner limits: mixed content in inline CSS and meta refresh, SPF without `all` or `redirect`, DMARC without the `;` after `v=DMARC1`: fix, or list under "what this scan does not check" | Scanner accuracy audit |
| P3 | Per-client permissions; logo in branding; bulk assign; scheduled report emails to a client | Agency audit |
| P3 | Per-workspace alert thresholds; stack-specific fix text | Monitoring and onboarding audits |
| P3 | Dark editorial design pass; free token allowance for the Action | Roadmap; developer-experience audit |
| P3 | Activation metrics beyond the funnel: pricing-section views (needs the notice changed in the same patch) | Analytics audit |

## 5. Recommended order

1. **Owner actions that need no code** (this week): sign up as a fresh user on the live site and record what happens (item 1); decide the backup approach (item 2); confirm the Cloudflare choice; check one real alert email and webhook.
2. **Small safety nets for a pilot** (one patch each): overdue-schedule warning and failed-mail indicator (4); backup script written and tested with you (2).
3. **Verify fix** with the resolved-state wording (3), because it is the main user-visible gap in the core promise.
4. **Portfolio usability** (8): small, frontend only, helps every user with more than a few sites.
5. **Load test and shared limits** (6), once there is a decision on whether a paid edge plan is acceptable.
6. **Agency client-level report and PDF cover** (9).
7. **Billing foundation** (5), starting in the Paddle sandbox and only after Paddle approves the seller account.
8. **Database roles** (7) and **public docs** (10) before any public launch.

Each step is its own small patch with tests, applied and pushed by you after your check.

## 6. Dependencies

- Items 5 and everything billing: Paddle approval, then sandbox, then the lifecycle test (create, upgrade, downgrade, cancel, renew, fail, refund).
- Item 6: your decision on paid Cloudflare or another shared store (costs money).
- Item 2: a read-only database role created in Neon by you; the script needs Windows, Docker and the real database, so it is built together with you.
- Item 1: your time and an email address that can receive the confirmation mail.
- Public launch: the Kleinunternehmer/VAT answer, the lawyer's review, and the processing agreements (section 11).

## 7. Security risks

**Open and honest:** the six PARTIAL security items are 12 (deletion without cancelling a subscription), 27 and 59 (database roles), 34 and 53 (limits), 60 (backups). Rate-limit counters and running-scan state are in one process's memory and reset on restart (items 34, 53); migrations run under the runtime database role (27, 59); a live subscription is not cancelled when an account is deleted, which matters once payments exist; the two NOT VERIFIED items (17 secret rotation, 62 branch protection) rest on owner statements; GitHub protections and the database password are Owner-reported only; no external penetration test has been done. Shared report links are bearer links (anyone with the link reads that report until it expires or is revoked); the interface says so.

**Risks new work must not add:** unscoped queries (every id route must filter by workspace); echoing submitted values in errors; secrets or tokens in logs, URLs or analytics; outbound requests that bypass the one validate-and-pin path; billing state taken from the browser instead of a verified provider event.

## 8. Testing requirements

Every patch: targeted tests first, then the full backend suite on PostgreSQL, ruff, mypy, the frontend lint, typecheck, format check, unit tests and build, the secret scan, and a deliberate break of the new rule to prove the test can fail. Billing work additionally needs sandbox-provider tests for duplicate, late and out-of-order events and a crash between recording and applying an event. A load test needs a defined target (users, scans per minute) before it is run, and its result must be recorded in `OPERATIONS.md`, not only reported. Browser tests run in CI only; run them before relying on a UI change.

## 9. Pilot-readiness criteria

**Controlled external pilot (free plans)** can start when all of these hold:
1. A fresh sign-up, email confirmation, site verification and first scan have been done on the live site by someone other than a developer, and the problems found are fixed or written down.
2. A backup is taken weekly and before every migration (by hand is acceptable for a few users), and the latest one has been restored at least once (done on 25 Oct).
3. The owner looks at Platform Health after each release (mail failures and server errors are shown there but nothing alerts).
4. Pilot users are told that this is a pilot, that paid plans do not exist yet, and how to reach support and report a security issue (the home page now shows both).
5. The owner accepts, knowingly, that the lawyer review and the VAT answer are still open for a free pilot.

**Paid commercial launch** additionally needs: items 5, 6 and 7 of the top ten; the Paddle sandbox lifecycle passed; the lawyer's review; the Kleinunternehmer/VAT decision and an invoice flow; a tested incident process and support mailbox that someone reads; and a second look at the security audit's PARTIAL items. Test results alone do not satisfy any of this.

## 10. Effort key

Small: one patch, under a day of work. Medium: a few patches, a few days. Large: a project with an external dependency or a design decision. These are estimates, not commitments.

## 11. Decisions that need the owner

1. **Backup approach:** Windows Task Scheduler with a read-only Neon role (recommended once there are real users), a GitHub Action (not recommended: production data on GitHub), or Neon's paid plan.
2. **Cloudflare:** keep the leaked-credential check and skip an edge rate limit (the default taken so far, option A), or switch the one free rule slot to a sign-in rate limit (option B).
3. **Paid edge or shared store** for rate limits, or accept in-memory limits for the pilot only.
4. **Kleinunternehmer status and VAT ID**; business-registration details; when to commission the lawyer's review.
5. **Data location:** the API host is in the US; whether to move it to Frankfurt (`OPERATIONS.md` section 8, `legal-audit.md`).
6. **Processing agreements** with the hosting, database, edge and mail providers: confirmed by you, to be kept on file.
7. **A free token allowance** so a developer can try the CI Action before paying.
8. **Rotate the Google sign-in secret** if the downloaded client-secret file was ever shared (you said it was not).
9. **The three unique commits** on the old backup branch `backup-project-polish-pro` in the portfolio backup folder: keep, push or discard.
10. **Pilot size and who the first users are.** Everything in section 9 scales with this.

## 12. Do not implement yet

- **Paid plans on sale, a checkout, or any "active subscription" screen** before Paddle approval and the sandbox lifecycle. Plans stay "Coming soon".
- **A payment webhook receiver in production** before the signature check, atomic apply and ordering rules exist and are tested.
- **Active or intrusive scanning** (anything beyond passive requests), crawling beyond the page and well-known files, or checks that send attack payloads. The product promise, the Terms and the abuse model all rest on passive checks.
- **Open or click tracking in emails, third-party analytics scripts, or longer retention of visit data** without a consent and notice review.
- **Caching, queues, extra indexes or paid infrastructure** without a measured need; the performance review found none.
- **Claims of certification, compliance, guaranteed protection, customer counts or reviews.** None exist, and none may be added without evidence.
- **A public API stability promise or hosted API reference** before the endpoints are reviewed and versioned.
- **Per-client permissions and a redesign of the whole interface** before pilot feedback shows they matter; each is a large change with its own design pass.

## Audit index

`product-improvement-audit.md` (baseline), `scanner-accuracy-audit.md`, `scanner-test-matrix.md`, `dashboard-and-portfolio-audit.md`, `monitoring-and-alerting-audit.md`, `reporting-audit.md`, `agency-workflow-audit.md`, `developer-experience-audit.md`, `onboarding-ux-audit.md`, `subscription-readiness-audit.md`, `operational-readiness-audit.md`, `marketing-and-documentation-audit.md`, `analytics-and-feedback-audit.md`, `performance-review.md`; earlier: `security-audit-summary.md`, `release-readiness-report.md`, `legal-audit.md`, `KNOWN_LIMITATIONS.md`, `ROADMAP.md`.
