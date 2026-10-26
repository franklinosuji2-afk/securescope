# What is left to do

Written 23 October 2026. Ordered by what matters most. "You" means the site owner; the rest is engineering work.

## Needs you

1. **Paddle.** Paid plans stay "Coming soon" until the seller account is approved. Then: checkout, subscription state,
   idempotent payment webhooks, billing page. Nothing is sold or shown as active before that.
2. **Try the GitHub Action** once on a real workflow run with a new API token (Integrations > API tokens for CI). The `v1` tag exists (24 October). If the repository stays private, other repositories need access (Settings > Actions > General).
3. **DNS hardening for getsecurescope.com** (the scan's own informational notes): add a CAA record, turn on DNSSEC in
   Cloudflare and add the DS record at the registrar, and move DMARC from `p=none` to `p=quarantine` once the
   reports show only your own senders.
4. **Check the first real alert email and a webhook** against a receiver you control (Integrations > Webhook alerts > Send
   test message). The first scheduled-scan alert email has not fired yet because nothing new has appeared.
5. **Check the sign-in icons** (Google and GitHub) in a private window.
6. **Local cleanup** (see the end of this page). Two files in Downloads hold secrets and should not stay there.
7. **Windows update.** The desktop workspace link is broken on this computer ("a Windows update prevents the workspace
   from reaching your files"). Install the latest Windows update and restart. File delivery still works.

8. **Legal questions only you can answer** (details in `docs/legal-audit.md`): are you a Kleinunternehmer (§ 19 UStG)?
   Render runs in Oregon (US), verified 24 October 2026: do you want to move it to Frankfurt (see
   `OPERATIONS.md` section 8)? You stated the data-processing terms are accepted. Is "early access" still the right
   wording (the Terms now say "in development")? Do you have any trade-register or professional-body details to show? Then
   have a German/EU lawyer read the three pages before paid plans open.

## Product

- **Slack alerts** are built (Integrations > Webhook alerts > "A Slack channel"): same triggers as the email and webhook alerts, incoming-webhook style, no evidence in the message. Not built: Microsoft Teams, interactive Slack features (buttons, a Slack app with sign-in).
- **Verification workflow.** Separate "no longer detected" from "confirmed resolved" (needs a later scan that examined
  the same resource), and add a "Verify fix" action that re-checks one finding.
  The re-check exists since 26 Oct ("Check if it is fixed" on a finding: one fresh look, nothing stored, never marks
  a finding resolved). Still open: letting a re-check that examined the same resource mark it resolved.
- **Premium PDF cover and layout**: done on 26 Oct. Page 1 is now a full cover: title, host, scope line, score and
  grade, risk rating, severity counts, a plain summary built only from the report's own findings (count, the top three
  problems), reference, dates and the disclaimer. Findings start on page 2, each kept whole on a page, with the same
  footer. The home-page sample PDF was regenerated. Still open: a table of contents for very long reports.
- **Dark editorial design system** across all pages (brief section 5): shared tokens and components, then apply page by
  page. Do this as its own project with screenshots at four widths, not mixed into feature work.
  The theme audit of 26 Oct (`docs/dark-mode-audit.md`) found both themes sound and fixed the flash of the wrong theme; this project is
  now about consistency of components, not about dark mode being broken.
- **Scan comparison** should say when two scans are not comparable (different checks ran, a check could not run).
- **Per-rule test audit.** Severity and score are pinned by tests; each of the 40 rules should also have a positive,
  a negative and an edge-case test, and its fix text re-read against the rule.
- **Agency**: client-level reports across all of a client's sites; scheduled report e-mails (not built, not promised).
- **Public API** with documented, versioned endpoints beyond the CI ones, still behind plan limits.

- **Audit-log retention** is built: 12 months, deleted hourly (`SECURESCOPE_AUDIT_RETENTION_DAYS`). The personal-data JSON export exists (Account > Your data).
- **Account and billing self-service, still open** (from the product brief): customer reviews and ratings (nothing
  exists yet, and no fake reviews), billing pages and plan changes (groundwork built: subscription tables, plan rule, downgrade preview; the provider part waits for Paddle), a legal-page audit against the
  code with a German/EU lawyer's review. Account deletion and data export already exist (`api/v1/account.py`).

## Engineering

- **Webhook delivery** retries failed alerts up to four more times over about 8.5 hours (since 26 Oct; the last 20 outcomes per address are listed on the Webhooks page). Still open: an alert if an address keeps failing.
- **Free hosting cold starts.** A paused backend needs up to a minute; the Action waits, the web app shows a loading
  state. A keep-warm ping or a paid instance removes it.
- **Releases.** Version is 0.11.0 in the API and 0.1.0 in package files; there is no changelog or tagged release.
- **Coverage audit** (`docs/ENGINEERING_COVERAGE_AUDIT.md`) should be re-counted after these additions.
- **Passive checks** to consider later, each with tests first: HTTP to HTTPS redirect chain details, `Set-Cookie`
  prefixes, `Cross-Origin-*` isolation headers. Nothing active or intrusive.
- **Scheduled backup** runs weekly from your PC (set up 25 Oct, `OPERATIONS.md` section 2). Still to do: a second encrypted copy away from the PC (the missed-run warning exists: `scripts/setup-backup-check.ps1`).
- **Edge rate limit** for the sign-in routes in Cloudflare (your dashboard action), then p99, concurrency and EXPLAIN checks.
- **Badge** could show the scan date in its image and offer a flat-square style.

## Done recently (for reference)

Passive page and DNS checks, scheduled scans, webhook alerts, GitHub Action, API tokens, score badges, plan tables on
every tier, new logo, score method in every report, severity policy with tests, DNS findings naming records instead of
a page; bounded database pool, log-leak tests, secret-rotation procedure and Dependabot (24 October).

## Local cleanup (run in PowerShell, check the list first)

These are already-applied patches and an empty backup, all safe to remove:

```
cd C:\Users\frank\Downloads
Remove-Item accuracy.patch, agency.patch, brand.patch, checks.patch, ci.patch, compare.patch, fix1.patch, motion.patch, plans-0009.patch, polish.patch, positioning.patch, premium.patch, remediation.patch, samplereport.patch, schedules.patch, score.patch, signin.patch, signin2_1.patch, signin2.patch, ui.patch, ui2.patch, webhooks.patch -ErrorAction SilentlyContinue
Remove-Item C:\Users\frank\signin.patch.bak
Remove-Item C:\Users\frank\securescope\backups\securescope-20261022-011656.dump, C:\Users\frank\securescope\backups\securescope-20261022-144610.dump
```

Look at these yourself before deleting; they were not removed automatically:

- `Downloads\client_secret_...apps.googleusercontent.com.json` holds the Google sign-in client secret. It is already set
  on Render, so delete the file (and rotate the secret in Google Cloud if the file was ever shared).
- `Downloads\env.txt` and `env (1).txt` (47 bytes each) look like copied settings. Open, check, delete.
- `C:\Users\frank\securescope\.env` is ignored by git; keep it local only.
- `C:\Users\frank\securescope\backups\*.dump` (the two non-empty ones) are database backups; keep or move them
  somewhere private. They are not in git.
- `C:\Users\frank\user_files.sha` and the other project folders in your home folder were not touched.
