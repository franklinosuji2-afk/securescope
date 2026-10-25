# Analytics and customer feedback audit

Date: 25 Oct 2026. Phase 11 of the product-quality brief. The existing analytics and feedback code was read first; one thing was added (an operator-only activation funnel). **No usage data is invented in this document**: the product has had no real external users yet, so there are no numbers to report, only what can and cannot be measured.

## Result

| Area | Status | In short |
|---|---|---|
| Public page-view counting | Existing, verified | Cookieless, public pages only, 90-day retention, honours Do Not Track and Global Privacy Control |
| Private customer feedback | Existing, verified | One entry per person, optional, withdrawable, read only by the operator |
| Product activation | **Gap, now closed for the operator** | Counted from rows that already exist; nothing new is tracked |
| Pricing viewed, upgrade initiated, GitHub Action configured | Not measurable | See "Events" |
| Metrics for repeat scanning, alerts and conversion | Defined here, mostly not yet computable | See "Metrics" |

## What already existed

- **Page views** (`docs/ANALYTICS.md`): eleven fixed public pages, a daily-changing one-way visitor hash, referrer host only, device class only, no IP address or browser string stored, no cookie or browser storage. Dropped for bots and opt-outs. Read only by the account whose confirmed email is the operator's.
- **Feedback** (`Account` page, `api/v1/feedback.py`): star rating 1 to 5, optional topic, optional comment up to 2000 characters. One entry per person, can be changed or withdrawn, deleted with the account, never shown to other customers. The operator sees totals and the latest entries without names or email addresses (Platform Health). The privacy notice names the purpose, the legal basis (consent) and the withdrawal right.
- **Audit log** (365 days): records account, website, scan, report and token actions with the workspace and a timestamp. It is for accountability, not analytics, but it is where "report downloaded" is already recorded.

## Events: tracked, implemented, proposed, needing review

| Event from the brief | Source today | Status |
|---|---|---|
| Account created | `organizations.created_at` | **Implemented** in the funnel (counts workspaces, not people) |
| Website added | `targets.created_at` | **Implemented** |
| Website verified | `targets.verified_at` | **Implemented** |
| First scan started | `scans.created_at` | Stored; not shown separately (the funnel uses completed, which is the meaningful step) |
| First scan completed | `scans` with status completed | **Implemented**, plus the median time from sign-up |
| Second scan completed | same | **Implemented** (scheduled and CI scans count too) |
| Report downloaded | audit event `report.downloaded` | **Implemented** (exports are a different event and are not counted) |
| Monitoring enabled | `scan_schedules` row | **Implemented** (a schedule that was later deleted no longer counts) |
| API integration activated | `api_tokens` row | **Implemented as "token created"**; first real use is not recorded |
| GitHub Action configured | lives in the customer's repository | **Proposed, not measurable**: the closest server-side signal is the first CI-started scan, which is not recorded as an event |
| Pricing page viewed | a section of the signed-out home page, not a page | **Proposed, needs privacy review**: it would add a counted view type; the privacy notice and its test list the counted pages and must change together |
| Upgrade initiated | no billing exists | **Not applicable until Paddle is live** |

## What was implemented

`GET /api/v1/analytics/activation?days=` (operator only, 404 for everyone else) and an "Activation" panel on the existing Analytics page.

- It counts, for workspaces created in the period (default 30 days), how many reached each step above and the median seconds from sign-up to first completed scan.
- It reads existing tables only. **No new event is collected, nothing is stored, no migration, no change to the privacy notice is needed.** The answer holds eleven fields: counts, a median and a small-cohort flag. It carries no workspace id, email, site name or URL (a test checks this).
- Fewer than five workspaces in the cohort is flagged on screen as "examples, not a trend".
- Tests: `test_activation.py` (6 tests: admin only, validation, empty period shows zeros, once per workspace, older workspaces and unfinished or failed scans excluded, no identifiers) and 2 frontend tests. Three mutation runs (counting any scan status, double-counting a workspace with two sites, a second scan counted at one) were each caught.

## Honest limits of the funnel

- It counts **workspaces**, not people; one person with two workspaces counts twice. The operator's own and test accounts are included, so with a handful of real users the numbers are dominated by them.
- Deleting a website or an account removes its rows, so later reports undercount (survivorship). Only the audit-based step survives a deleted website.
- The cohort is by creation date, so the latest days are incomplete by nature; read 30 or 90 days, not 7.
- It cannot show **why** someone stopped; that needs feedback or an interview.

## Metrics to use (definitions; none has real data yet)

| Metric | Definition | Computable now |
|---|---|---|
| Activation | Workspaces with a completed scan, divided by workspaces created | Yes (funnel) |
| Time to first successful scan | Median seconds, sign-up to first completed scan | Yes (funnel) |
| Verification drop-off | Added but not verified | Yes (funnel) |
| Repeat scanning | Workspaces with a second completed scan within 14 days of the first | Partly: the second scan is counted, the 14-day window is not |
| Monitoring adoption | Workspaces with a schedule, divided by workspaces with a verified site | Yes, from two funnel counts |
| Report downloads | Workspaces that downloaded at least one report | Yes (funnel) |
| Alert usefulness | Alerts opened or acted on, and alerts followed by a fix | **No**: alert emails carry no tracking by design, and a finding's later resolution is not tied to the alert |
| Conversion | Upgrades initiated and completed, divided by activated workspaces | Not until billing is live |

## Recommendations

1. **Use the funnel only after real people sign up.** Until then it describes the owner's own test accounts.
2. **Do not add tracking to alert emails.** Open and click tracking would need consent and a notice change; alert usefulness is better measured by asking (item 4) and by whether a finding is later marked resolved.
3. **Pricing views:** count a pricing-section view as one more public page name only after the notice and `legal.test.tsx` are updated in the same change. Low value until paid plans exist.
4. **Feedback prompts:** feedback lives only on the Account page, which new users rarely open. A single optional prompt after the first completed scan, with a dismiss, would give far more answers than any event count. The prompt must not block anything. A "this finding looks wrong" link on each finding would also feed scanner accuracy work.
5. **Keep collecting nothing else.** Credentials, tokens, full URLs, finding details and report contents must stay out of any future event; the funnel's field list is the model.

## Requires privacy or consent review before any change

- Any new per-person or per-visit event, any tracking in emails or reports, any third-party analytics script, and any longer retention than 90 days for visit data.
- The lawyer review of the privacy notice is still open (see the marketing audit); it should cover the funnel's existence (aggregate counts from service records for the operator's legitimate interest) even though it introduces no new data.

## Statuses for this phase

- Local development: READY.
- Owned or authorised sites: READY WITH CONDITIONS.
- Controlled external pilot (free plans): READY WITH CONDITIONS. Page views, feedback and an activation funnel exist and are privacy-conservative; interpret them with the limits above.
- Public commercial launch: NOT READY (no conversion measurement, no alert-usefulness signal, privacy notice review pending).
