# What is left to do

Written 23 October 2026. Ordered by what matters most. "You" means the site owner; the rest is engineering work.

## Needs you

1. **Paddle.** Paid plans stay "Coming soon" until the seller account is approved. Then: checkout, subscription state,
   idempotent payment webhooks, billing page. Nothing is sold or shown as active before that.
2. **Tag the GitHub Action.** `git tag v1` and `git push origin v1`, so `uses: franklinosuji2-afk/securescope/action@v1`
   resolves. If the repository stays private, other repositories need access (Settings > Actions > General). Try the
   Action once on a real workflow run with a new API token (Targets > API tokens for CI).
3. **DNS hardening for getsecurescope.com** (the scan's own informational notes): add a CAA record, turn on DNSSEC in
   Cloudflare and add the DS record at the registrar, and move DMARC from `p=none` to `p=quarantine` once the
   reports show only your own senders.
4. **Check the first real alert email and a webhook** against a receiver you control (Targets > Webhook alerts > Send
   test message). The first scheduled-scan alert email has not fired yet because nothing new has appeared.
5. **Check the sign-in icons** (Google and GitHub) in a private window.
6. **Local cleanup** (see the end of this page). Two files in Downloads hold secrets and should not stay there.
7. **Windows update.** The desktop workspace link is broken on this computer ("a Windows update prevents the workspace
   from reaching your files"). Install the latest Windows update and restart. File delivery still works.

## Product

- **Slack integration** (next in the agreed order). Same triggers as the email and webhook alerts, incoming-webhook
  style, no evidence in the message.
- **Verification workflow.** Separate "no longer detected" from "confirmed resolved" (needs a later scan that examined
  the same resource), and add a "Verify fix" action that re-checks one finding.
- **Premium PDF cover and layout** from the product brief: a cover page with reference, dates, scope and an executive
  summary; keep each finding together on a page; consistent footer. The score method, DNS wording and scope notes are
  done.
- **Dark editorial design system** across all pages (brief section 5): shared tokens and components, then apply page by
  page. Do this as its own project with screenshots at four widths, not mixed into feature work.
- **Scan comparison** should say when two scans are not comparable (different checks ran, a check could not run).
- **Per-rule test audit.** Severity and score are pinned by tests; each of the 40 rules should also have a positive,
  a negative and an edge-case test, and its fix text re-read against the rule.
- **Agency**: client-level reports across all of a client's sites; scheduled report e-mails (not built, not promised).
- **Public API** with documented, versioned endpoints beyond the CI ones, still behind plan limits.

- **Account and billing self-service, still open** (from the product brief): customer reviews and ratings (nothing
  exists yet, and no fake reviews), billing pages and plan changes (wait for Paddle), a legal-page audit against the
  code with a German/EU lawyer's review. Account deletion and data export already exist (`api/v1/account.py`).

## Engineering

- The **Targets page is long** (domains, schedules, webhooks, badges, tokens). Move integrations to their own page.
- **Webhook delivery** is best effort (two attempts, no queue). A small retry queue would help receivers that are down.
- **Free hosting cold starts.** A paused backend needs up to a minute; the Action waits, the web app shows a loading
  state. A keep-warm ping or a paid instance removes it.
- **Releases.** Version is 0.11.0 in the API and 0.1.0 in package files; there is no changelog or tagged release.
- **Coverage audit** (`docs/ENGINEERING_COVERAGE_AUDIT.md`) should be re-counted after these additions.
- **Passive checks** to consider later, each with tests first: HTTP to HTTPS redirect chain details, `Set-Cookie`
  prefixes, `Cross-Origin-*` isolation headers. Nothing active or intrusive.
- **Badge** could show the scan date in its image and offer a flat-square style.

## Done recently (for reference)

Passive page and DNS checks, scheduled scans, webhook alerts, GitHub Action, API tokens, score badges, plan tables on
every tier, new logo, score method in every report, severity policy with tests, DNS findings naming records instead of
a page.

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
