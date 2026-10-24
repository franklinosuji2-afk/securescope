# Operations runbook

For the person running SecureScope. Everything here assumes the free-tier setup in `DEPLOY_FREE.md`: Cloudflare (static site, Worker proxy, DNS, Email Routing), Render (API), Neon (Postgres), Brevo (mail).

Menus in provider dashboards change. If a path below does not match, search the dashboard for the feature name.

## 1. Is it up? (monitoring)

Set up one free external monitor so you hear about an outage before a user does.

1. Create a free account at UptimeRobot (the free plan lists 50 monitors, 5-minute checks and e-mail alerts; check the current terms).
2. Add an **HTTP(s)** monitor for `https://getsecurescope.com/api/v1/ready`. It returns 200 with `{"status":"ready"}` when the API can reach the database, and 503 otherwise.
3. Add a second monitor for `https://getsecurescope.com/` (the static site).
4. Send alerts to an e-mail address you read on your phone.

Side effect to know: a ping every 5 minutes keeps the free Render instance from sleeping. That removes cold starts but uses its free monthly hours continuously. Check Render's current free-hours limit before relying on it.

In-app view: **Platform Health** (admin only). Its request and e-mail figures are in memory and reset on every restart (`MONITORING.md`).

## 2. Backups

Neon's free plan keeps only a short history window for restore (6 hours by default at the time of writing, see the [Neon docs](https://neon.com/docs/introduction/point-in-time-restore)). Anything older than that cannot be recovered from Neon alone, so take your own backup.

**Take a backup** (Windows, Docker Desktop running):

```
$env:SECURESCOPE_BACKUP_URL = "<Neon connection string>"
.\scripts\backup-db.ps1
Remove-Item Env:SECURESCOPE_BACKUP_URL
```

The script writes `backups\securescope-<time>.dump` (ignored by git) and checks the file can be read back. The connection string is typed only into your own shell; never paste it anywhere else.

**The backup contains user e-mail addresses and password hashes.** Keep the file on an encrypted disk or in a private cloud folder and delete old copies.

**Prove it works** (do this once now, then after any schema change):

```
.\scripts\restore-test.ps1 backups\securescope-<time>.dump
```

It restores into a throw-away local PostgreSQL container, prints a row count per table and the schema version, then deletes the container.

Suggested rhythm: before every release that includes a migration, and at least weekly while real users exist.

Status: the dump/restore commands were tested against a real PostgreSQL 16 in the development environment (identical row counts and schema version after restore). The PowerShell wrappers have not yet been run on your PC with Neon; run them once and record the date here: `_not yet run_`.

## 3. Restoring

| Situation                                               | What to do                                                                                                                                                                                                                                         |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A bad change or deletion within the Neon history window | Use Neon's instant restore, or restore to a new branch and compare. See the Neon docs above.                                                                                                                                                       |
| Older damage, or the Neon project is gone               | Create a new Neon database, restore your latest `.dump` into it with `pg_restore --no-owner --no-privileges -d <new connection string> <file>`, then set `SECURESCOPE_DATABASE_URL` in Render to the new string. The API runs migrations on start. |
| Lost a Render service                                   | Re-create it from `render.yaml`, then re-enter its secrets (see section 5).                                                                                                                                                                        |
| Lost the Cloudflare Worker                              | Redeploy from git (`wrangler.jsonc`), then re-set `BACKEND_URL` and `PROXY_SECRET`.                                                                                                                                                                |

After any restore: sign in, open Targets and Scan History, and run one scan of a verified site.

## 4. Rolling back a bad release

Code and database are separate, so decide which one broke.

- **Frontend or API code:** the fastest safe path is `git revert <commit>` then `git push`. CI runs, Cloudflare rebuilds and Render redeploys. Both providers also let you redeploy an earlier build from their dashboards (Cloudflare: the Worker's Deployments tab; Render: the service's Events/Deploys list).
- **A migration:** do not roll back by hand. Restore from a backup taken before the release (section 3) and deploy the previous code. Migrations are forward-only in practice.
- After rolling back, rescan a verified site and check the Platform Health page.

Take a backup before any release that adds a migration.

## 5. Secrets and rotation

| Secret                                                                   | Set in                            | Rotate when                                                                                                                                                                                               |
| ------------------------------------------------------------------------ | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Neon connection string                                                   | Render                            | A leak, or yearly. Create the new password in Neon, update Render, confirm `/ready`, then revoke the old one.                                                                                             |
| `PROXY_SECRET` / `SECURESCOPE_TRUSTED_PROXY_SECRET`                      | Cloudflare and Render (identical) | A leak. Change both, Render last.                                                                                                                                                                         |
| Mail API key (Brevo)                                                     | Render                            | Before it expires (note the date when you create it) or on a leak.                                                                                                                                        |
| `SECURESCOPE_CRON_SECRET` (Render) and `CRON_SECRET` (Cloudflare Worker) | Render, Cloudflare                | Anyone could trigger due scans early (they stay verified-site-only and within plan limits). Change both values together.                                                                                  |
| `SECURESCOPE_WEBHOOK_SIGNING_KEY`                                        | Render                            | A leak. Every endpoint's signing secret is derived from it, so changing it makes all existing secrets invalid: each receiver must then be given its new secret (Targets > Webhook alerts > Renew secret). |
| `SECURESCOPE_ANALYTICS_SALT`, `SECURESCOPE_METRICS_TOKEN`                | Render                            | A leak. Changing the salt only resets the daily visitor hashes.                                                                                                                                           |

If a secret was pasted somewhere public, treat it as leaked and rotate it immediately.

### Rotation procedure (any secret)

Do this in order so the service never runs with mismatched values. Never type a secret into chat, an issue or a commit.

1. **Create the new value** in the provider (Neon, Brevo, Google or GitHub OAuth) or generate a random one locally
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Keep the old value working.
2. **Set the new value** in the place listed in the table (Render dashboard, Cloudflare Worker settings). For a pair
   (`CRON_SECRET`, `PROXY_SECRET`) change the Cloudflare side first and the Render side last, then wait for the Render
   redeploy.
3. **Check**: `https://getsecurescope.com/api/v1/ready` returns 200; sign in; for mail, trigger a password reset to
   yourself; for OAuth, sign in with that provider; for the cron secret, the next scheduled run completes.
4. **Revoke the old value** in the provider. Do this last.
5. **Record** the date and secret name (never the value) in the verification log below.

Extra secrets not in the table: `SECURESCOPE_DOWNLOAD_SIGNING_KEY` (download links live only a few minutes, so a change
only invalidates links that are already open), `SECURESCOPE_OAUTH_GOOGLE_CLIENT_SECRET` and
`SECURESCOPE_OAUTH_GITHUB_CLIENT_SECRET` (rotate in the provider console, then update Render).

**If a secret leaked**: rotate it at once (steps 1 to 4), then look for use between the leak and the rotation: Neon and
Render logs, unexpected scans or audit-log events. For a leaked database string also rotate the Neon role password and
treat stored e-mail addresses as exposed and ask a lawyer whether a GDPR breach notification (Art. 33/34) applies.
If the secret is in git history, rotating is the fix; rewriting history does not undo the exposure.

Dependabot (`.github/dependabot.yml`) opens weekly update pull requests for Python, npm, GitHub Actions and the two
Dockerfiles. Review and merge them yourself; CI must be green first.

## 6. Incidents

1. **Confirm:** is `https://getsecurescope.com/api/v1/ready` green? Does the site load?
2. **Contain:** if the cause is a recent release, roll back (section 4) first and investigate after.
3. **Look:** Render logs (JSON lines with a request ID), Platform Health, Cloudflare Worker logs.
4. **Fix, then verify:** run one scan of a verified site and open a finding.
5. **Write it up** within a few days using `INCIDENT_TEMPLATE.md`, even for a short outage. Keep the file in `docs/incidents/`.

Common cases:

- **API returns 503 on `/ready`:** the database is unreachable. Check Neon status and the connection string in Render.
- **First request after idle is slow (30-60 seconds):** Render free instance was asleep. Expected without a monitor ping.
- **Sign-up works but no e-mail arrives:** provider outage or key problem. The log shows `mail send failed` with a status code, never the key.
- **Everyone is rate-limited:** the Worker secret and the Render secret differ, so every visitor looks like one address. Re-set both.

## 7. Recovery targets (honest numbers)

These are what the setup can deliver today, not promises.

- **Data loss window:** up to the age of your latest backup (plus Neon's 6-hour history if the problem is recent). Without your own backups it is only that 6-hour window.
- **Time to recover:** a few hours by hand with this runbook. Not rehearsed on production.
- **Single points of failure:** one API instance, one database, one maintainer. See `KNOWN_LIMITATIONS.md`.

## 8. Moving the API to Frankfurt (decision pending)

The API service `securescope-api` currently runs in Oregon (verified 24 October 2026) while the database is in Frankfurt.
Moving it keeps the application server in the EU and removes the transatlantic hop (database checks currently take
about half a second). Render cannot change a service's region, so this means a new service:

1. In Render create a new web service from the same repository and Dockerfile, region **Frankfurt**, with the same
   environment variables (copy each value in the dashboard; never paste them elsewhere).
2. Wait until `/api/v1/ready` on the new `onrender.com` address returns 200.
3. In Cloudflare set the Worker variable `BACKEND_URL` to the new address; check sign-in, a scan and `/api/v1/ready` through
   `getsecurescope.com`.
4. Update the privacy notice ("United States, Oregon" becomes "Germany, Frankfurt") and the checklist in the same
   release; keep the old service for a day, then delete it.

## Scheduled scans

A Cloudflare cron trigger (every 15 minutes, `frontend/wrangler.jsonc`) calls `POST /api/v1/internal/run-due` on the
API with the header `X-Cron-Secret`. That wakes a sleeping free-tier API, runs up to three due scans, and emails
workspace owners, admins and security analysts only when a scan finds something new or the score falls by 5 points
or more. The endpoint is answered with 404 unless `SECURESCOPE_CRON_SECRET` is set, and the public proxy never
forwards `/api/v1/internal/*`.

Set-up: pick 32 or more random characters and set the same value as `SECURESCOPE_CRON_SECRET` on Render and as the
`CRON_SECRET` secret on the Worker (Cloudflare > Workers > securescope > Settings > Variables and Secrets). Deploy
the Worker so the cron trigger registers. Check: Cloudflare > the Worker > Triggers shows the cron, and a schedule's
"Last run" on the Targets page fills in within about 15 minutes. Scheduled scans count toward the monthly allowance.

## Webhook alerts

On the same triggers as the alert email, a workspace can have a signed JSON message sent to up to three HTTPS
addresses (Targets > Webhook alerts). The feature stays off, and says so on the page, until
`SECURESCOPE_WEBHOOK_SIGNING_KEY` (32 or more random characters) is set on Render. No secret is stored in the
database: each endpoint's signing secret is derived from that key, the endpoint id and a version number, and is shown
once when the endpoint is added or its secret is renewed. Messages carry `X-SecureScope-Signature: t=<seconds>,v1=<hex>`
(HMAC-SHA256 over `<t>.<raw body>`). The address is checked as for scan targets, when saved and before each delivery
(public addresses only, connection pinned, no redirects, reply body never read). A failure is retried once; ten
failures in a row switch the endpoint off until a person switches it on. Check: add an address, press "Send test
message" and look for the result under the address.

## CI tokens and badges

No new setting is needed. Tokens and badges use the database (migration `0013`). To cut off a token someone leaked,
revoke it under Targets > API tokens for CI; to cut off a leaked badge address, use "New address" or switch the badge off.
Token digests are SHA-256 of a 256-bit random value, so there is no key to rotate. Details: `docs/INTEGRATIONS.md`.

## Verification log

Dated proof that the procedures above were actually carried out. Add a line each time one is repeated.

| Date       | What was checked                                                                                                                     | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-10-23 | Backup of the production database with `scripts/backup-db.ps1`, restored into a throw-away container with `scripts/restore-test.ps1` | Passed. Schema version 0013; 24 tables restored, including `scan_schedules`, `api_tokens`, `webhook_endpoints` and `site_badges`. An earlier run against an older database branch (schema 0009) was discarded: always compare the host in the Render `SECURESCOPE_DATABASE_URL` with the one you back up, and check the restored schema version against the newest migration.                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2026-10-23 | External monitors (UptimeRobot, 5-minute checks, e-mail alerts) on `/api/v1/health`, `/api/v1/ready` and the site                    | Alert e-mail received. An earlier false alarm (HTTP 405 on `HEAD`) was fixed on 2026-10-22: the health and ready routes accept `HEAD`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 2026-10-23 | Scheduled scans                                                                                                                      | A schedule created on the live site ran by itself (2026-10-22 22:30, completed). A second run followed on 2026-10-23 at 22:45 (completed, score 100), so the cron path is confirmed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2026-10-23 | Cloudflare settings for the domain                                                                                                   | SSL/TLS mode Full (strict); Cloudflare Free Managed Ruleset on; Bot Fight Mode on.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 2026-10-23 | Two-factor sign-in                                                                                                                   | Reported on for the Google account used to sign in to GitHub, Render, Neon, Cloudflare and the registrar, and for GitHub.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 2026-10-24 | Security review (secrets, configuration, dependencies)                                                                               | Full git history searched for key, token, private-key and credentialed-URL patterns: nothing real (only test values). `pip-audit`, `npm audit` and `bandit` clean. Live headers checked: HSTS, CSP, nosniff, frame and referrer policies present; `/.env` and `/.git/config` return the app page, not files; `/metrics` and the cron route are not reachable without their secrets. Found and fixed: the Swagger docs page and OpenAPI schema were public on the site's own origin (now off unless `SECURESCOPE_API_DOCS_ENABLED=true`), and the Worker's block on `/api/v1/internal` could be bypassed with a percent-encoded path (the cron secret still protected the route; now decoded before the check, and `x-cron-secret` is stripped from visitor requests). **After deploying, check that `https://getsecurescope.com/api/docs` returns 404.** |

Still not done: a regular (scheduled) backup, a rehearsed rollback, and a rate-limit rule for the sign-in routes at the edge.
