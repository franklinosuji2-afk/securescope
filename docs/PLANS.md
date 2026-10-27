# Plans and limits

Every workspace (organization) has one plan. The server decides what the plan allows; the browser only shows it.

|                                                                         | Free    | Professional | Agency      |
| ----------------------------------------------------------------------- | ------- | ------------ | ----------- |
| Price (hypothesis, not charged yet)                                     | €0      | €19 / month  | €49 / month |
| Websites                                                                | 1       | 5            | 20          |
| Scans per calendar month                                                | 3       | 30           | 150         |
| Scan history kept                                                       | 30 days | 90 days      | 365 days    |
| Invite teammates and clients                                            | no      | no           | yes         |
| Client workspace (clients, dashboard, agency name on PDFs, share links) | no      | no           | yes         |
| Scheduled scans (daily or weekly) with email and webhook alerts         | no      | yes          | yes         |
| GitHub Action and API tokens for CI                                     | no      | yes          | yes         |
| Public score badge (opt-in, per verified site)                          | yes     | yes          | yes         |

An internal plan (no limits, 365 days, can invite) is given automatically to workspaces owned by the operator (`SECURESCOPE_ADMIN_EMAIL`). It cannot be bought. The prices are assumptions to test, not commitments.

## Where it lives

- `app/billing/plans.py`: the catalogue (the only place limits are written down).
- `organization_plans` table (migration 0009): one row per workspace that has a plan. **No row means the default plan, Free.** An unknown plan id also behaves as Free.
- `app/billing/entitlements.py`: looks up a workspace's plan and its usage.
- `GET /api/v1/organizations/{id}/plan` (owner/admin): plan, limits and usage, shown on the Account page. When a subscription exists it also reports its status, period end, whether it ends and any pending downgrade.
- `subscriptions` and `billing_events` tables (migration 0016): groundwork for a billing provider. **Nothing writes them yet**, so every workspace's plan is exactly what it was before. `billing_events` holds only the provider's event id and type, so a repeated delivery is recognised and ignored; no payload is kept.
- `app/billing/lifecycle.py`: the rule for which plan applies (below).
- `GET /api/v1/organizations/{id}/plan/downgrade-preview?to=<plan>` (owner/admin): read-only list of what a lower plan would exceed or lose (`app/billing/preview.py`).

## App Scanning (provisional; not offered, not advertised)

Code and dependency checks are being built as a separate module (`docs/app-scanning-v1-*.md`). The plan catalogue already carries starting values so the server can enforce them once routes exist; **nothing is sold, shown to customers or reachable yet** (`SECURESCOPE_APP_SCANNING_ENABLED` is off and there are no routes).

|                                                    | Free                     | Professional | Agency | Internal |
| -------------------------------------------------- | ------------------------ | ------------ | ------ | -------- |
| App Scanning runs per calendar month (provisional) | 5                        | 100          | 500    | no limit |
| App Scanning projects (placeholder)                | 1                        | 10           | 50     | no limit |
| App Scanning CI tokens                             | no (browser upload only) | yes          | yes    | yes      |

Rules (decisions of 26 Oct 2026): runs have their own counter and never use up website scans, or the reverse. One accepted request for one project is one run. Rejected requests, failed runs and interrupted runs are not counted; a retry with the same idempotency key returns the first run and is not counted again. A per-project hourly limit (`SECURESCOPE_APP_SCANS_PER_PROJECT_PER_HOUR`, placeholder 6) is counted in the database. Website limits, tokens and permissions are unchanged. These numbers are hypotheses; the Free plan keeps no CI access because tokens stay a Professional feature.

## Which plan applies

1. The internal plan (the operator's own workspaces) is never changed by a subscription.
2. No subscription: the workspace keeps the plan it has (Free unless one was assigned).
3. A paid subscription gives its plan while the paid period lasts, including a cancelled one or one that is behind on payment: what was paid for stays until the period ends, and not longer.
4. After the period ends, a requested downgrade starts (only if the subscription is still active); otherwise the workspace returns to the plan it had before.
5. A subscription can only name a plan that can be bought (Professional or Agency), never Free, internal or an unknown id.

## Counting rules

- Websites: the rows in `targets` for the workspace. Removing a site frees its slot.
- Scans: scans created since 00:00 UTC on the 1st of the month, **except failed scans**, which are not counted. The allowance renews at the start of the next month.
- Limits are checked inside the same database transaction that inserts the row, after locking the workspace row (`SELECT ... FOR UPDATE` on PostgreSQL), so simultaneous requests cannot exceed a limit. SQLite has a single writer, so it needs no lock.
- A refused request returns HTTP 403 with a plain message. The existing 429 rate limits (per client and per site per hour) still apply on top.

## Downgrades and over-limit workspaces

Nothing is deleted early. A workspace over a limit (for example after a downgrade) keeps every site, scan and report and can still run existing sites if scans remain; it is only blocked from adding new sites or scans. Scan history older than the new plan's window is removed by the hourly maintenance job, together with its findings and reports.

## Not built yet

Payment (Paddle sandbox first, then live after approval), the webhook receiver that fills the subscription tables, the billing page, cancelling from the app, annual billing, a job queue for scans, and scheduled scans. Do not advertise a feature on this page until it exists. Before real payments: accurate reports, customer isolation, backend-enforced limits (done), secure idempotent webhooks, sustainable pricing, and no advertised feature that does not exist.

## Load and storage notes

Scans still run inside the API process (at most 3 at once, a few requests each), so the 150-scan Agency allowance is the ceiling to watch. PDF reports are stored in the database; at tens of kilobytes each, 365 days of Agency history is small, but Neon's free storage should be monitored.

A read-only audit of limits, states and billing readiness is in [subscription-readiness-audit.md](subscription-readiness-audit.md).
