# Legal pages audit

Date: 24 October 2026. Scope: the three legal pages (Impressum, Privacy notice, Terms of use) checked against the
code and configuration in this repository. This is engineering support, not a legal opinion. Items marked **Lawyer**
need a qualified German/EU review; items marked **Operator** need a fact only the operator knows.

## 1. Pages and routes

| Page           | Route         | Source                                       |
| -------------- | ------------- | -------------------------------------------- |
| Impressum      | `#/impressum` | `frontend/src/pages/Legal.tsx` (`Impressum`) |
| Privacy notice | `#/privacy`   | same file (`Privacy`)                        |
| Terms of use   | `#/terms`     | same file (`Terms`)                          |

Footer links to all three: landing page footer (`Landing.tsx`), sign-in and registration pages (`LegalLinks`), the
signed-in app (`App.tsx`). A tab bar on each legal page links the three. Contact addresses come only from
`frontend/src/contact.ts` (tests: `contact.test.tsx`). Operator name and address are constants at the top of
`Legal.tsx`. The date shown is the `UPDATED` constant.

## 2. Claims checked against the code

| Statement                                                                                     | Evidence                                                                                                                                                      | Result                                                                                                          |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Account data: email, salted password hash, workspace name                                     | `models/account.py` (`users`, `organizations`); `security/passwords.py`                                                                                       | Verified                                                                                                        |
| Two session cookies, one OAuth cookie of ten minutes                                          | `api/v1/auth.py` (`ss_session` httponly, `ss_csrf` readable, both SameSite=Lax, Secure when configured), `api/v1/oauth.py` (`ss_oauth`, `max_age=600`)        | Verified                                                                                                        |
| No other cookies                                                                              | no other `set_cookie` in the backend; frontend reads only the CSRF cookie                                                                                     | Verified                                                                                                        |
| **Browser storage** (theme, selected workspace, pending invitation)                           | `theme.ts` (localStorage `securescope-theme`), `auth.tsx` (sessionStorage `securescope.org`), `pendingInvite.ts` (sessionStorage `securescope.invite`)        | **Was missing from the notice. Added.**                                                                         |
| Visit statistics: no cookie, no stored IP, daily hash, DNT and GPC honoured, 90 days          | `services/analytics.py`, `api/v1/analytics.py` (DNT, `Sec-GPC`, bots skipped), `models/analytics.py` (no IP or browser column), maintenance loop in `main.py` | Verified                                                                                                        |
| Pages counted                                                                                 | `TRACKED_PAGES` includes home, sample report and Agency features                                                                                              | **Notice listed too few pages. Corrected.**                                                                     |
| "Hash is one-way, so we cannot recognise you on another day"                                  | HMAC-SHA256 over day, address and browser string, key from `analytics_salt`                                                                                   | Accurate, but the value is pseudonymous. **Notice now says it is treated as personal data.**                    |
| Audit log "and your IP address"                                                               | `AuditEventRow` has no IP column; the rate limiter keeps addresses in memory only (`middleware/ratelimit.py`)                                                 | **Inaccurate. Corrected: audit log has no IPs; in-memory abuse counters described separately.**                 |
| Audit log "kept only as long as needed"                                                       | no cleanup job; events live until the workspace is deleted                                                                                                    | **Unsupported. Now says "until the workspace is deleted".** A retention period is a decision (section 6).       |
| Scan history deleted after 30/90/365 days by plan                                             | `repositories/scans.delete_expired_history`, hourly loop in `main.py`; reports go with the scan                                                               | Verified. Note: the loop runs only while the API process is awake; the 15-minute Cloudflare cron keeps it awake |
| Invitations deleted a month after expiry                                                      | `purge_old_invitations`                                                                                                                                       | Verified                                                                                                        |
| Account deletion immediate, needs password                                                    | `api/v1/account.py`, `repositories/accounts.delete_account`; tests in `test_client_accounts.py`                                                               | Verified                                                                                                        |
| Deletion also removes schedules, API tokens, webhook addresses, badges, clients, plan records | foreign keys are `ON DELETE CASCADE`; **no test covered this**                                                                                                | **New tests added** (`test_account_deletion_data.py`); they pass                                                |
| Backups still hold deleted data for a time                                                    | `DATA_RETENTION.md`; Neon restore history; local dumps                                                                                                        | **Notice did not say so. Added.**                                                                               |
| Only verified domains are scanned                                                             | `api/v1/scans.py` (`find_verified`), `api/v1/ci.py`, `services/scheduler.py`                                                                                  | Verified for manual, CI and scheduled scans                                                                     |
| DNS lookups: SPF, DMARC, CAA, DNSSEC                                                          | `scanner/dns_checks.py` (TXT, `_dmarc` TXT, CAA, DS)                                                                                                          | Verified. Ownership proof also reads one TXT record (`security/ownership.py`)                                   |
| Scheduled-scan, webhook, token and badge descriptions                                         | `models/*`, `services/alerts.py`, `services/webhooks.py`                                                                                                      | Verified                                                                                                        |
| Emails: only service emails, no marketing                                                     | `services/mailer.py`, `services/auth.py`, `services/alerts.py`                                                                                                | Verified                                                                                                        |
| Providers                                                                                     | Cloudflare (`frontend/worker`, `wrangler.jsonc`), Render (`render.yaml`), Neon, Brevo (`render.yaml`, `services/mailer.py`)                                   | In use. Neon region is Frankfurt (`eu-central-1` in the connection host). Render region **Operator**            |
| Google and GitHub listed under "processors"                                                   | `services/oauth.py`: they authenticate the user for their own purposes                                                                                        | **Inaccurate (they are separate controllers). Corrected.**                                                      |
| EU-US Data Privacy Framework or SCCs for transfers                                            | not verifiable from the repository                                                                                                                            | **Operator / Lawyer**: confirm each provider's current certification or contract                                |
| Early access wording in Terms                                                                 | paid plans "Coming soon"; free plan live                                                                                                                      | Plausible; **Operator** to confirm                                                                              |
| Subscription terms                                                                            | no billing code exists (`grep -i paddle` finds nothing)                                                                                                       | Terms now say paid plans are not on sale and that payment terms will be added first                             |

## 3. Statements corrected in this round

1. Visit statistics: full list of counted pages; hash described as personal data.
2. Audit log: no IP addresses; kept until the workspace is deleted. In-memory abuse counters described on their own.
3. New paragraph on the three browser-storage items.
4. Google and GitHub are not processors; Neon location stated; transfer sentence no longer asserts one mechanism for all.
5. Backups, restore history and hosting logs after deletion.
6. Required versus optional data; no automated decisions.
7. "Scanning other people's sites" renamed "How scanning works" (the old heading suggested scanning third-party sites, which the product does not do); ownership methods named.
8. Terms: verification is technical control, not permission; suspension reasons; ending use matches the real deletion flow and the sole-owner rule; no payment terms invented; material changes announced before they apply.
9. Analytics page text lists the counted pages. `docs/PRIVACY.md` said "not yet written"; it now points here.

## 4. Impressum

| Point                                                         | Finding                                                                                                                                                                                       |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "§ 5 DDG"                                                     | Correct statutory reference since the Digitale-Dienste-Gesetz replaced the TMG (May 2024). Keep.                                                                                              |
| Name, postal address, email                                   | Present. A telephone number is not required when another fast electronic contact exists (email); **Lawyer** to confirm.                                                                       |
| "No VAT identification number has been issued"                | **Removed 24 Oct**: VAT status is unconfirmed, so the claim was unsupported. Previously: true as stated, but says nothing about the small-business rule (§ 19 UStG). **Operator**: are you a Kleinunternehmer? Prices shown (EUR 19, EUR 49) must follow that choice when sales start. |
| "Responsible for content (§ 18 Abs. 2 MStV)"                  | Applies to services with journalistic-editorial content; SecureScope publishes none. Harmless to keep; kept and documented. **Lawyer** may remove.                                            |
| Consumer dispute resolution notice (VSBG § 36)                | Required only for businesses above a staff threshold; not added. The EU ODR platform link ended in 2025 and must not be added. **Lawyer** to confirm.                                         |
| Trade or professional register, chamber, regulated profession | Not applicable as far as the repository shows. **Operator**: confirm that you have no trade registration number or professional-body details that must be shown.                              |

## 5. Privacy notice: remaining gaps

- Legal bases are given per item. The reliance on Art. 6(1)(f) for statistics and the audit log, and on 6(1)(b)/(f) for invitations, should get **Lawyer** review.
- Storing the theme, workspace and invitation items is treated as strictly necessary for the requested service (§ 25 Abs. 2 Nr. 2 TDDDG). No consent banner is shown. **Lawyer** to confirm. The visit statistics use no device storage.
- Hosting logs (Cloudflare, Render) are governed by those providers' retention; the notice says so but gives no period. **Operator**: check each provider's log settings.
- Processor agreements (Art. 28) with Cloudflare, Render, Neon and Brevo and their transfer terms: **Operator** to confirm they are accepted in each dashboard.
- Brevo is described as "Brevo (Sendinblue SAS), France". Confirm the contracting entity.
- Audit-log retention: decide on a period (suggested: 12 months) and add a cleanup job, or keep "until the workspace is deleted".
- No self-service data export exists; the notice says to ask by email. A JSON export would remove the manual step.
- The supervisory authority named (Berlin) is right for an operator based in Berlin.

## 6. Terms: remaining questions

- Liability clause is the usual German pattern (unlimited for intent, gross negligence, injury; limited for slight negligence to essential duties and typical foreseeable damage). **Lawyer** to confirm it holds in a consumer and a business setting.
- "Early access": remove when the operator decides the service is no longer in that phase.
- When paid plans start: price including or excluding VAT, billing period, renewal, cancellation, withdrawal right for consumers and the checkout information duties must be added and shown during checkout (Paddle acts as merchant of record; read its terms). **Lawyer / Operator.**
- The promise to announce material changes is a commitment: **Operator** to confirm it will be kept.

## 7. Technical items affecting privacy claims

| Item                                                        | Status                                                   |
| ----------------------------------------------------------- | -------------------------------------------------------- |
| Deletion of rows in newer tables                            | Tested now                                               |
| Audit-log retention job                                     | Not built                                                |
| Self-service export of personal data                        | Not built                                                |
| Log-leak test (no secrets or addresses in application logs) | Not built; roadmap                                       |
| Request lines in Render's own platform logs                 | Outside the application; **Operator** to check retention |
| Cookie names and flags match the notice                     | Verified in code; check once in the browser after deploy |

## 8. Order of work

1. (done) Corrections above, with tests.
2. Operator answers: VAT status (Kleinunternehmer), Render region (verified: Oregon, USA; privacy notice updated), processor agreements (operator states accepted), early-access status (Terms now say "in development"), trade registration.
3. Audit-log retention decision and job; data export.
4. Lawyer review of the three pages before paid plans open.
