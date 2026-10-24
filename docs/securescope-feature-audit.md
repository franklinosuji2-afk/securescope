# SecureScope feature audit

Date: 24 October 2026. Scope: the account, subscription, deletion, review and additional-service areas of the brief.
Method: reading the repository at commit `3a9f799` plus the flake fix; test counts are from runs recorded in
`docs/OPERATIONS.md` and this session. Classes: **VERIFIED** (implemented and covered by a test), **UNVERIFIED**
(implemented, no test or not checked live), **PARTIAL**, **MISSING**, **N/A**, **BLOCKED** (needs an external
dependency).

## 1. Account and onboarding

| Capability | Class | Evidence |
| --- | --- | --- |
| Registration, sign-in, logout, refresh | VERIFIED | `api/v1/auth.py` (`/register`, `/login`, `/logout`, `/refresh`, `/me`); `tests/test_auth.py` |
| Email verification | VERIFIED | `/verify-email`, `/resend-verification`; `require_verified_email` setting; `tests/test_client_accounts.py` |
| Password reset | VERIFIED | `/forgot-password`, `/reset-password` (reset revokes sessions); `tests/test_auth.py`, `tests/test_log_secrets.py` |
| Google and GitHub sign-in | VERIFIED | `api/v1/oauth.py`, `services/oauth.py`; `tests/test_oauth.py` |
| Password change | VERIFIED | `api/v1/account.py` (`PATCH /password`) |
| Onboarding checklist | UNVERIFIED | `frontend/src/overview.ts` (`add`, `verify`, `scan`, `review` steps) shown on Overview; unit-tested in `src/test`, not end to end |
| Profile name / display name | MISSING | `models/account.py` `UserRow` has email only |
| Session or device list, sign out other devices | VERIFIED (Phase 1) | `GET/DELETE /account/sessions`, `POST /account/sessions/revoke-others`; Account > Signed-in devices; `tests/test_account_settings.py` |
| Account status, creation date | VERIFIED (Phase 1) | `GET /account`; Account > Your account |

## 2. Plans and entitlements

| Capability | Class | Evidence |
| --- | --- | --- |
| Central plan catalogue | VERIFIED | `billing/plans.py` (Free, Professional, Agency, Internal); no literals elsewhere |
| Backend enforcement (websites, scans per month, history, schedules, invites, client workspace) | VERIFIED | `billing/entitlements.py`, `repositories/plans.py`, `lock_organization`; `tests/test_plans.py`, `tests/test_cross_customer.py` |
| Plan, usage and limits shown | VERIFIED | `Account.tsx` "Your plan"; `PlanComparison.tsx` on the landing page |
| Subscription record (status, period, provider ids) | PARTIAL | table, effective-plan rule and idempotent event log built and tested (`billing/lifecycle.py`, `repositories/billing.py`, migration 0016, `test_subscriptions.py`); nothing writes it until a provider is connected; usage still counts calendar months |
| Upgrade, downgrade, cancel | BLOCKED | no billing provider code; Paddle seller account not approved |
| Invoices, billing history, payment methods | BLOCKED | same |
| Over-limit handling after a downgrade | VERIFIED (preview) | nothing is deleted; `GET .../plan/downgrade-preview` lists what exceeds or is lost; existing enforcement blocks only new additions (`test_subscriptions.py`, `test_plans.py`) |

## 3. Account settings

| Capability | Class | Evidence |
| --- | --- | --- |
| Unified settings area | PARTIAL | `Account.tsx` has plan, password, deletion only |
| Notification preferences | MISSING | no model or endpoint; alert emails are per schedule (`models/schedule.py`, `services/alerts.py`) |
| Personal-data export | VERIFIED (Phase 1) | `GET /account/export`; `tests/test_account_settings.py` |
| Privacy preferences | N/A | analytics is cookie-free and honours DNT/GPC; nothing to configure |
| Domain and scan management within limits | VERIFIED | Targets, History, Compare pages; limit errors in `billing/errors.py` |

## 4. Account deletion

| Capability | Class | Evidence |
| --- | --- | --- |
| Self-service deletion with password and confirmation | VERIFIED | `api/v1/account.py` (`DELETE`); `repositories/accounts.py`; `tests/test_client_accounts.py` |
| Sole-owner hand-over rule | VERIFIED | same; Terms section 6 |
| Every newer table removed | VERIFIED | `tests/test_account_deletion_data.py` (added this session) |
| Active subscription handling | BLOCKED | no subscriptions exist yet; Phase 4 must cancel through the provider (or refuse deletion until it is cancelled) before deleting; the subscription row is removed with the account (`test_subscriptions.py`) |
| Asynchronous deletion status | N/A | deletion is immediate and transactional |
| Deletion audit record | UNVERIFIED | deleted accounts have no rows left by design; operator-level log not present |

## 5. Reviews and feedback

| Capability | Class | Evidence |
| --- | --- | --- |
| Private feedback (1 to 5 stars, topic, comment; edit and withdraw) | VERIFIED | `models/feedback.py`, `repositories/feedback.py`, `api/v1/feedback.py`, migration `0015`; `test_feedback.py` (rating bounds, one entry per user, other users cannot read it, deleted with the account, operator summary without names or emails); Account page "Your feedback" in `account.test.tsx` |
| Operator view of feedback | VERIFIED | `GET /feedback/summary` (administrators only, 404 otherwise); Platform health "Customer feedback" panel |
| Public reviews with moderation | MISSING | not ready: needs real customers, a moderation path and legal wording |

## 6. Additional services

| Item | Class | Evidence |
| --- | --- | --- |
| 1 Scheduled scans | VERIFIED | `api/v1/schedules.py`, `services/scheduler.py`; `tests/test_schedules.py`; live run 23 Oct 22:45 |
| 2 Scan history and tracking | VERIFIED | `History.tsx`, `repositories/scans.py`; retention per plan |
| 3 Domain and subdomain monitoring | MISSING | no subdomain discovery (also keeps scope from expanding silently) |
| 4 TLS certificate monitoring | PARTIAL | `scanner/tls.py` `days_remaining`, expired finding; no "expires soon" alert on its own |
| 5 Uptime and broken-link monitoring | MISSING | |
| 6 Custom scan profiles | MISSING | |
| 7 Priority scanning | MISSING | not promised anywhere (kept out of the copy) |
| 8 PDF and CSV exports | VERIFIED | `api/v1/scans.py` export (html, md, json, csv); PDF `reporting/pdf.py`; `tests/test_pdf_report.py`, `tests/test_compare_csv.py` |
| 9 Branded client reports | VERIFIED | `api/v1/agency.py`; `tests/test_agency.py` |
| 10 Scan comparison | VERIFIED | `Compare.tsx`, finding lifecycle; `tests/test_finding_lifecycle.py` |
| 11 Email alerts | VERIFIED | `services/alerts.py`, `services/mailer.py` (Brevo); first real alert email still to see in production |
| 12 Webhook alerts | VERIFIED | `services/webhooks.py` signed, retried twice; `tests/test_webhooks.py`; delivery history (last 20 per address: time, event, outcome, attempts; no content) since migration 0017, listed on the Webhooks page |
| 13 Slack | MISSING | |
| 14 Microsoft Teams | MISSING | |
| 15 GitHub Action | VERIFIED | `action/`, `api/v1/ci.py`; `tests/test_github_action.py`; no `v1` tag yet |
| 16 Public API | PARTIAL | API tokens can start and read scans for CI only; stated on the pricing page |
| 17 to 19 Teams, clients, roles | VERIFIED | `api/v1/invitations.py`, `agency.py`, `security/permissions.py`; `tests/test_invitations.py`, `test_tenancy.py` |
| 20 Usage dashboard | PARTIAL | Account shows usage; Overview shows scans and findings; no single page |
| 21 Security header evaluation | VERIFIED | `scanner/checks.py` weak and present checks; `tests/test_checks_and_scoring.py` |
| 22 Compliance readiness | N/A | deliberately not offered; the product says it is not a certification |

## 7. Scanner safety

Verified by tests: SSRF matrix (`tests/test_ssrf_matrix.py`), target validation (`test_target.py`), redirects and
fetcher limits (`test_fetcher.py`), verified-only scanning in scans, CI and scheduler, scan cancel and concurrency
limit (`test_scan_control.py`), injection payloads (`test_injection_payloads.py`). No change in this plan weakens them.

## 8. Existing bugs and security concerns found

1. Sessions could not be listed or revoked individually: fixed in Phase 1.
2. Account deletion leaves no operator-side record; acceptable for privacy, but note it.
3. No audit-log retention job (also in `legal-audit.md`).
4. Webhook delivery is still best effort: two tries, no retry queue. A failure after the second try is shown in the delivery history but is not retried later.
5. Nothing found that exposes another customer's data; `tests/test_cross_customer.py` and `test_tenancy.py` pass.

## 9. Reuse rather than recreate

`billing/plans.py` and `entitlements.py` (extend with subscription state), `organization_plans` (extend, keep `source`),
`services/mailer.py` and `services/alerts.py` (notification preferences hook in here), the audit log (`api/v1/audit.py`)
for billing and review events, `Account.tsx` (becomes the settings centre), the sole-owner deletion flow.
