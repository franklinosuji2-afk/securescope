# Domain verification: what changed

Date: 25 Oct 2026. Follows `docs/domain-verification-audit.md` (row numbers below refer to its findings). Nothing was run against live DNS or production data; no live migration was run.

## Changes

| Audit row | Change | Where |
|---|---|---|
| 10 | On a successful check the challenge token and its expiry are erased | `repositories/targets.py::record_check` |
| 9 | An expired token is no longer returned by the API (status `expired`, empty values); the periodic maintenance step erases the stored value | `to_out`, `purge_expired_challenges`, `main.py` maintenance loop |
| 11 | New action `DELETE /targets/{id}/challenge` removes the active challenge and keeps the site and any verification; audit event `target.challenge_removed` | `api/v1/targets.py`, `clear_challenge` |
| 14 | A success is stored only if the token that was checked is still the active one (row lock plus comparison). If the owner replaced or removed the challenge during the check, the result is "replaced or removed while the check ran" and nothing is verified | `record_check` |
| 13 | `POST /targets/{id}/challenge` uses the same per-target hourly limit as verification, with its own counter | `api/v1/targets.py` |
| 18 | Reassurance text on the verification screen; an expired or removed challenge shows "no active challenge" instead of a dead value; "Remove challenge" button; the verified card says the value was removed | `pages/Targets.tsx` |
| (support) | Migration `0019`: `challenge_token` and `challenge_expires_at` become nullable. Downgrade gives rows without a challenge an already-expired random one | `alembic/versions/0019_challenge_nullable.py` |

A lapsed proof (180 days) whose challenge was erased answers 409 "There is no active challenge. Press New challenge…".

## The five points from the request

| Point | Status |
|---|---|
| The token is single-purpose | It is used only by the two ownership checks and is not accepted anywhere else. Stated on the screen |
| It expires automatically | 7 days, enforced on every verify; after that the value is hidden and erased |
| New challenge and remove the old one | "New challenge" replaces the value (the old one stops working at once); "Remove challenge" clears it |
| Minimum data, no expired tokens kept | Erased on success, on removal and after expiry (the cleanup runs with the other periodic jobs, so an expired value can remain in the database for up to one cycle, but the API never returns it) |
| After verification, show Verified and remove the token | The card shows Verified with date and method, and the API returns no token |

## Decisions and limits

- **No hashing.** The value must be shown to the owner so they can publish it, and it is public once published. Shortening how long it is kept is the safer control here.
- **The rate limiter is in memory**, so the limit is per server instance. One instance runs today.
- **Not changed:** copy buttons for the name and value (cosmetic), the HTTP file method, hostname validation, scanner integration.
- **Owner action when deploying:** the migration runs automatically at start-up and takes a short lock on `targets`. Take a backup first (the weekly one counts, or run `scripts/backup-db.ps1`).
