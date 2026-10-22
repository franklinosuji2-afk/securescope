# Plans and limits

Every workspace (organization) has one plan. The server decides what the plan allows; the browser only shows it.

| | Free | Professional | Agency |
|---|---|---|---|
| Price (hypothesis, not charged yet) | €0 | €19 / month | €49 / month |
| Websites | 1 | 5 | 20 |
| Scans per calendar month | 3 | 30 | 150 |
| Scan history kept | 30 days | 90 days | 365 days |
| Invite teammates and clients | no | no | yes |

An internal plan (no limits, 365 days, can invite) is given automatically to workspaces owned by the operator (`SECURESCOPE_ADMIN_EMAIL`). It cannot be bought. The prices are assumptions to test, not commitments.

## Where it lives

- `app/billing/plans.py`: the catalogue (the only place limits are written down).
- `organization_plans` table (migration 0009): one row per workspace that has a plan. **No row means the default plan, Free.** An unknown plan id also behaves as Free.
- `app/billing/entitlements.py`: looks up a workspace's plan and its usage.
- `GET /api/v1/organizations/{id}/plan` (owner/admin): plan, limits and usage, shown on the Account page.

## Counting rules

- Websites: the rows in `targets` for the workspace. Removing a site frees its slot.
- Scans: scans created since 00:00 UTC on the 1st of the month, **except failed scans**, which are not counted. The allowance renews at the start of the next month.
- Limits are checked inside the same database transaction that inserts the row, after locking the workspace row (`SELECT ... FOR UPDATE` on PostgreSQL), so simultaneous requests cannot exceed a limit. SQLite has a single writer, so it needs no lock.
- A refused request returns HTTP 403 with a plain message. The existing 429 rate limits (per client and per site per hour) still apply on top.

## Downgrades and over-limit workspaces

Nothing is deleted early. A workspace over a limit (for example after a downgrade) keeps every site, scan and report and can still run existing sites if scans remain; it is only blocked from adding new sites or scans. Scan history older than the new plan's window is removed by the hourly maintenance job, together with its findings and reports.

## Not built yet

Payment (Paddle sandbox first, then live after approval), subscription state and webhooks, billing page, annual billing, a job queue for scans, and scheduled scans. Do not advertise a feature on this page until it exists. Before real payments: accurate reports, customer isolation, backend-enforced limits (done), secure idempotent webhooks, sustainable pricing, and no advertised feature that does not exist.

## Load and storage notes

Scans still run inside the API process (at most 3 at once, a few requests each), so the 150-scan Agency allowance is the ceiling to watch. PDF reports are stored in the database; at tens of kilobytes each, 365 days of Agency history is small, but Neon's free storage should be monitored.
