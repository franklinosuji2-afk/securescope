# Website analytics

Cookieless visit counting for the **public pages only** (home when signed out, sign-in, registration,
forgot/reset password, email confirmation, Impressum, Privacy, Terms). Signed-in use of the app is never
counted. The dashboard is visible only to the operator account.

## What is stored (table `page_views`)
| Column | Content |
| --- | --- |
| `occurred_at` | UTC timestamp |
| `page` | one of a fixed list of page names (anything else is rejected) |
| `referrer_host` | host name of the linking site only; no path or query; empty for direct visits and our own host |
| `device` | `desktop`, `mobile` or `tablet`, derived from the browser string, which is not kept |
| `visitor` | HMAC-SHA256 of (UTC day, client address, browser string) keyed with `SECURESCOPE_ANALYTICS_SALT`, truncated to 32 hex characters. It changes every UTC day and cannot be reversed. |

Not stored: IP address, browser string, cookies, any identifier on the device (the tracker uses no
cookie, localStorage or sessionStorage). The address is read in memory to build the hash and for the
per-client rate limit, then discarded.

## Collection
`POST /api/v1/analytics/collect` with `{"page": "...", "referrer": "..."}` (referrer optional, first view
only). It answers `204` in every case, including when a view is dropped. Views are dropped for bots,
missing browser strings, `DNT: 1`, `Sec-GPC: 1`, over-rate clients (`SECURESCOPE_ANALYTICS_EVENTS_PER_CLIENT_PER_HOUR`,
default 60) and when `SECURESCOPE_ANALYTICS_ENABLED=false`. The front end additionally skips counting when
the browser reports Do Not Track or Global Privacy Control, and never counts a signed-in person.

## Reading
`GET /api/v1/analytics/summary?days=7|30|90&tz=Europe/Berlin` (any `days` 1 to 90). Allowed only for the
account whose **confirmed** email equals `SECURESCOPE_ADMIN_EMAIL`; everyone else gets `404`. `/auth/me`
returns `is_admin` so the UI can show the Analytics entry. The dashboard shows only recorded data and an
explicit empty state; it never shows sample numbers.

## Setup
1. On the API host (Render) set `SECURESCOPE_ADMIN_EMAIL` to the operator's email, and
   `SECURESCOPE_ANALYTICS_SALT` to a long random string (a password manager can generate one). Without a
   salt a random one is generated at every start, so unique counts split at each restart.
2. Make sure that account's email address is confirmed.
3. Open a public page in a private window, then check **Analytics**.

## Retention
Rows older than `SECURESCOPE_ANALYTICS_RETENTION_DAYS` (default 90) are deleted by the hourly maintenance
task. The privacy notice states 90 days; change both together.

## Limits
See `docs/KNOWN_LIMITATIONS.md` (visitor counting method, time-zone boundary, in-process summing).
