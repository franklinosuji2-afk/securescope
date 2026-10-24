# SecureScope implementation plan

Companion to `securescope-feature-audit.md` (24 October 2026). Rule for every phase: small change, tests first for
anything touching authorisation or data, no secrets, no production changes, nothing pushed without approval, no fake
billing or reviews. Phases ship as separate patches so each can be checked and deployed on its own.

## Decisions taken from the audit

- **Billing is blocked** on Paddle approving the seller account. Phase 3 builds only the groundwork that is correct
  whichever provider is used (state model, lifecycle rules, over-limit preview). No checkout, no webhook receiver and no
  success state is simulated.
- **Reviews:** start with private feedback. A public review page needs real customers, moderation and legal wording first.
- **Notification preferences:** the only emails today are service emails, per-schedule alerts (already configurable on the
  schedule) and security emails. Offering switches for announcements, billing or marketing mail that does not exist would
  be dead controls. Revisit when billing emails exist. Security and legally required mail never gets a switch.
- **Not planned:** subdomain discovery, uptime and broken-link monitoring, custom profiles, priority scanning, Teams,
  compliance checks. Each either widens scan scope, promises something the infrastructure does not guarantee, or risks a
  misleading claim. Slack is a candidate after Phase 4.

## Phases

| Phase | Work | Depends on | Acceptance |
| --- | --- | --- | --- |
| 1 | Account settings centre: account details (created, status, verified), sign-in sessions list with revoke and "sign out other devices", personal-data export (JSON download) | none | Each endpoint scoped to the signed-in user; another user's session cannot be listed or revoked; export contains only the caller's data and no password hash, tokens or other customers; tests for each; UI states for loading, empty, error |
| 2 | Private feedback: one rating (1 to 5), optional category and text per user; edit and withdraw; never required for any other action; nothing shown publicly | 1 | Invalid rating rejected; one row per user (update replaces); other users cannot read it; withdrawal deletes it; deleted with the account; no seeded rows |
| 3 | Subscription groundwork: `subscriptions` and `billing_events` tables (migration 0016, built 24 Oct), effective-plan rule (paid access kept until period end after cancellation), downgrade preview that lists what would exceed a lower plan, never deleting anything | none | Entitlements unchanged for every existing account; duplicate provider events are idempotent in unit tests; preview endpoint reads only |
| 4 | Billing provider integration (Paddle): checkout, webhook receiver with signature check, cancel, downgrade, invoices link | Paddle approval, credentials supplied by you in the host dashboard | Verified provider events only; no state change on unverified input; sandbox tests before any live use |
| 5 | Webhook delivery history (built, migration 0017), TLS "expires soon" alert (already covered by the scanner finding and the alert rule; test added), usage page (already on Account > Your plan, nothing added), `v1` tag for the GitHub Action (your git command) | none | Tests per item |
| 6 | Slack notifications | 5 | Only to a user-supplied incoming-webhook URL, validated like the webhook addresses (SSRF rules), signed test message |

## Cross-cutting checks per phase

Authorisation at the API and data layer; cross-customer test for every new endpoint; migrations reversible where
practical and never destructive; no secrets in logs (`test_log_secrets.py` extended when new tokens appear); mypy, ruff,
bandit, vitest, Playwright and build run and reported; docs and `legal-audit.md` updated when data handling changes.
