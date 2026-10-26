# App Scanning v1: plan entitlements

Date: 26 Oct 2026. A report and a proposal. **No limit has been added or changed, and no billing or provider setting was touched.** Facts come from `billing/plans.py`, `billing/entitlements.py`, `repositories/plans.py`, `api/v1/ci.py`, `billing/preview.py` and `docs/PLANS.md`, read on 26 Oct 2026.

## 1. Current plan definitions

|                                                       | Free    | Professional | Agency      | Internal |
| ----------------------------------------------------- | ------- | ------------ | ----------- | -------- |
| Price (hypothesis, not charged)                       | €0      | €19 / month  | €49 / month | n/a      |
| Websites                                              | 1       | 5            | 20          | no limit |
| Web scans per calendar month                          | 3       | 30           | 150         | no limit |
| History                                               | 30 days | 90 days      | 365 days    | 365 days |
| Scheduled scans, alerts, **CI tokens and the Action** | no      | yes          | yes         | yes      |
| Invite teammates / client workspace                   | no / no | no / no      | yes / yes   | yes      |

## 2. Existing usage accounting

Web usage is the count of `ScanRow` rows created since 00:00 UTC on the 1st, excluding failed scans, checked in the insert transaction with a row lock on PostgreSQL. The period is the UTC calendar month ("a billing provider's own period replaces this once subscriptions exist"). Websites are counted from `targets`. Nothing counts anything App Scanning-like.

## 3. Billing compatibility

- No payment provider is connected; `subscriptions` and `billing_events` exist but nothing writes them. Plans come from `organization_plans` (default Free) until a subscription exists.
- Adding fields to the `Plan` dataclass and the catalogue is compatible with the lifecycle rules (they select a plan id; limits come from the catalogue).
- Public pages and `docs/PLANS.md` say not to advertise a feature before it exists. App Scanning must not appear in plan tables until it works.
- When Paddle is connected later, the billing provider needs no knowledge of App Scanning allowances if they stay in the catalogue. Nothing in this proposal changes provider settings.

## 4. Do the existing model and the proposed values fit?

| Proposed                                              | Fits?                                                                                                                             | Notes                                                                                                   |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Free 5 / Professional 100 / Agency 500 runs per month | **Technically yes**: add `app_scans_per_month: int \| None` to `Plan` (None for Internal), counted from the new `app_scans` table | Needs a counter separate from `ScanRow` so web and app usage do not consume each other                  |
| Free can use App Scanning                             | **Conflict** for CI: the Action and tokens need `scheduled_scans`, which Free lacks                                               | Free could be limited to browser manifest upload, or the owner may allow App Scanning CI tokens on Free |
| Values relative to web                                | Different in kind                                                                                                                 | Web: 3 / 30 / 150. App: 5 / 100 / 500. Not wrong, but the unit ("run") must be defined                  |

## 5. Cost implications (estimates, not measurements)

- Per run on our side: parse a small file, one batched lookup call, insert findings. For CI submissions: validate JSON, re-check for secrets, insert. No scanner runs on our infrastructure in v1.
- Pressure points on the free infrastructure (0.1 CPU, 512 MB, Neon free storage): CPU while parsing and normalising up to 20 000 packages, memory for a 2 MB upload, and storage of findings rows. Agency at 500 runs is five times today's 150-scan ceiling in request count, though lighter per request. **No load figure exists for App Scanning**; a measured load test is a required step before any number is published.
- Third-party cost: the dependency lookup may be free, but terms and fair use are unverified (see privacy document, V3). A hosted-API dependency means our availability depends on theirs.
- Storage: findings are retained per `history_days`; size per run is unmeasured.

## 6. Decisions for the owner

| #   | Decision            | Options                                                                                                                                                                   |
| --- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Definition of a run | (a) one submitted scan of one project (recommended); (b) per scan kind; (c) per package looked up. Failed and unsupported runs not counted, matching the web rule         |
| D2  | Free plan access    | (a) browser upload only, no CI (no plan-rule change, recommended to start); (b) CI tokens for App Scanning on Free (changes who can hold tokens and widens abuse surface) |
| D3  | Allowance values    | Accept 5 / 100 / 500 as the starting hypothesis, or change after the load test                                                                                            |
| D4  | Counter             | Separate counter (recommended) versus a shared pool with web scans                                                                                                        |
| D5  | Projects limit      | A per-plan cap on projects, to bound storage (value open)                                                                                                                 |
| D6  | Rate limits         | Per project per hour in addition to monthly (value open)                                                                                                                  |

## 7. Implementation outline (after approval only)

1. Add `app_scans_per_month` (and `app_projects` if D5) to `Plan`; update `docs/PLANS.md` in the same batch.
2. Add a repository `app_usage()` and check it in the same transaction as the insert, with the same lock pattern.
3. Extend the Account page usage block and `downgrade_effects` (over-limit message, nothing deleted early).
4. Server-side 403 with a plain message; the 429 limits stay on top.
5. Tests: limit reached, concurrent requests, failed run not counted, web usage unchanged, Free/CI behaviour per D2, downgrade preview, Internal unlimited.

No migration is needed for plan values (they live in code); the tables for App Scanning need one additive migration, which is not run in production without approval.

## 8. Decisions approved on 26 Oct 2026 (recorded; none implemented yet)

| #      | Decision                                                              | Consequence for the build                                                                                                                                                                                                                                                                                                                                                                      |
| ------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D-A    | The server calls OSV when dependency lookup is built                  | Lookup is its own step (D), behind gates G1, G3 and G4 in the privacy document. Out of scope for Step B                                                                                                                                                                                                                                                                                        |
| D1     | One run is one accepted App Scanning request for one project          | Counted when the accepted request is stored. Invalid or unsupported requests are not counted. Findings never make a run unsuccessful. Infrastructure and scanner failures do not consume a run. A retry with the same idempotency key returns the first result and is not counted again. Partial and interrupted outcomes get explicit states (`incomplete`, `interrupted`) and are not hidden |
| D2     | Free supports browser upload only                                     | Free must not receive App Scanning CI tokens. Web Scanning tokens, the Action and `scheduled_scans` stay exactly as they are. The App Scanning token scope is a separate flag that Free's plan does not have, checked on the server                                                                                                                                                            |
| D3     | 5 / 100 / 500 stay provisional                                        | Held as configuration, not as binding commercial limits. No billing change                                                                                                                                                                                                                                                                                                                     |
| D4     | Separate usage counter                                                | Counted from the new App Scanning table, never from `ScanRow`. Web limits unchanged                                                                                                                                                                                                                                                                                                            |
| D5, D6 | Per-plan project caps and per-project hourly rate limits are required | Proposed as configuration below                                                                                                                                                                                                                                                                                                                                                                |

**Where each lands:** run accounting, the counter, token scope and the Free restriction need the `app_scans` table, so they are Step C (tables and counter) and Step H (tokens), not Step B. Step B delivered only the redaction module and canary harness; no accounting test exists yet because no accounting code does.

## 9. Proposed configuration for D5 and D6 (not final, not enforced)

The existing code puts rate limits in `Settings` (`scans_per_client_per_hour`, `scans_per_target_per_hour`, `max_concurrent_scans`) and plan limits in `billing/plans.py`. The same pattern is proposed:

| Name (proposed)                  | Where                       | Starting value                     | Basis                                                                                                                                      |
| -------------------------------- | --------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `app_projects` per plan          | `Plan` field                | Free 1, Professional 10, Agency 50 | **A placeholder, not evidence.** Web sites are 1 / 5 / 20; projects are cheap but bound storage. Revisit after storage per run is measured |
| `app_scans_per_project_per_hour` | `Settings`, env-overridable | 6                                  | **Placeholder.** Web uses 3 per site per hour; App Scanning runs are lighter but CI can loop                                               |
| `app_scans_per_client_per_hour`  | `Settings`                  | 20                                 | **Placeholder**, same reasoning as web's 10 per client                                                                                     |
| `max_concurrent_app_scans`       | `Settings`                  | 1                                  | Matches the 0.1 CPU instance; parsing is CPU-bound                                                                                         |

No final production value is set. The evidence needed first: parse time for a 2 MB lockfile and 20 000 packages on the real instance size, rows and bytes stored per run, and the dependency database's own limits (unverified). The in-memory limiters reset on restart and are per instance; that limitation is the same as for web scans and is documented, not hidden.
