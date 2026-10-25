# Subscription readiness audit

Date: 25 Oct 2026. Phase 8 of the product-quality brief. Scope: subscription state and usage limits, read from the code and checked by tests and mutation runs. **No payment was started, no billing-provider setting was touched, and no Paddle approval or payment is assumed.** Paddle approval is pending; paid plans are correctly shown as "Coming soon" and no screen offers a checkout.

## Result

| Area | Status | In short |
|---|---|---|
| Server-side limits | Verified | Websites and monthly scans are counted and inserted under one lock; features are gated by the plan on the server |
| Dashboard, API, CI and scheduled jobs agree | Verified, one test added | All ask `Entitlements.plan_for`; the three scan counters are now pinned together by a test |
| Subscription states | Verified for active, past due and cancelled; trial and paused are not modelled | See "States" |
| Upgrade, downgrade, cancellation | Verified in the rule; no UI, nothing to click yet | A downgrade never deletes data |
| Usage reset | Verified | Calendar month in UTC |
| Duplicate billing events | Partly ready | Repeats are recognised; late and out-of-order events and crash safety are not handled (see "Before Paddle") |
| Webhook verification | Not built | There is no receiver. This is correct while approval is pending |
| Entitlement escalation | None found | Four mutations of the limit rules were each caught by tests |
| False claim that billing is ready | None found | Landing page, plan table, terms and in-app messages all say "not on sale yet" |
| **Defect found and fixed** | History clean-up ignored the subscription | See "Defect fixed" |

## Defect fixed: history clean-up used the stored plan, not the plan that applies now

`delete_expired_history` chose each workspace's history window from the stored base plan only. A paying customer's plan comes from the subscription row, so the clean-up would have treated Professional (90 days) and Agency (365 days) customers as Free (30 days) and deleted scans, findings and reports they had paid to keep. It could not hurt anyone yet because nothing writes subscriptions, but it would have started on the first paid customer.

- **Fix:** the clean-up now works out the plan that applies now (subscription during the paid period, otherwise the stored plan, otherwise Free) with the same rule as every other check.
- **Tests:** three new tests in `test_subscriptions.py` (Professional keeps 60 days and loses 100; Agency keeps 300; a subscription whose paid period has ended returns to the Free window). Two of them failed before the fix. Mutation check: reverting to the base plan fails two tests.

## What was verified

**Server-side enforcement.** The plan catalogue (`billing/plans.py`) is the only place limits are written, and every enforcement point asks `Entitlements.plan_for`:

| Limit | Enforced in | Notes |
|---|---|---|
| Websites | `repositories/targets.py` | Count and insert under one organisation lock, so two requests cannot both take the last slot |
| Scans per month | `repositories/scans.py` | Same lock; failed scans do not count, cancelled ones do |
| Scheduled scans | `api/v1/schedules.py`, `services/scheduler.py` | The scheduler re-checks the plan on every run and switches the schedule off if the plan no longer includes it |
| API tokens and CI | `api/v1/integrations.py`, `api/v1/ci.py` | A workspace that loses the plan cannot start CI scans (`test_integrations`) |
| Webhook alerts | `api/v1/webhooks.py` | |
| Invitations | `api/v1/organizations.py` | Agency only |
| Clients, branding, share links | `api/deps.py`, `api/v1/agency.py` | Also on the public share route |
| History window | `repositories/scans.py` | Fixed above |

The browser never decides: the plan page only displays what the server returns.

**Usage reset.** The month is the calendar month in UTC (`current_period`), tested across December to January. The app shows the renewal time in the viewer's time zone (for example 1 Nov, 01:00 in Berlin), which is the same instant.

**Consistency.** The month's scan count is written three times (plan page, downgrade preview, the check that refuses a scan) with the same filter. A new test creates scans, fails some and checks that all three agree and that the limit check refuses and allows at the right boundary. Next step if the code is touched again: one shared counting function.

**Isolation.** Usage is per organisation (`test_one_workspaces_usage_never_counts_against_another`); a client role cannot see billing, and nobody can read another workspace's plan or downgrade preview.

**Escalation.** A subscription can only grant a plan that can be bought (never Free, Internal or an unknown id); the Internal plan is never changed by a subscription; an unknown status changes nothing; access never outlives the paid period; once the period is over the answer does not change as time passes. These are property-style tests in `test_subscription_invariants.py`. Four mutation runs (monthly limit off by one, paid access never ending, website limit removed, history clean-up using the base plan) each failed 2 to 8 tests, and the code was restored afterwards.

## States

| State | Behaviour |
|---|---|
| No subscription | Keeps the stored plan, Free by default |
| Active | Gets the subscribed plan while the paid period lasts |
| Past due | Keeps the plan until the period ends, not a day longer |
| Cancelled (or set to end) | Keeps the plan until the period ends, then returns to the earlier plan |
| Requested downgrade | Starts when the period ends, only for an active subscription |
| Expired | Back to the previous plan; nothing is deleted, additions beyond the limits are refused |
| **Trial** and **paused** | **Not modelled.** Paddle can report both. An unknown status deliberately changes nothing, so a trial would give no plan until the mapping is decided |

A downgrade only stops new additions. The history clean-up is the one place data is removed, and it follows the plan that applies now. The scheduler switches off schedules a plan no longer includes; after an upgrade they must be switched on again by hand, and the downgrade preview says so.

## Before Paddle: what must exist (none of it exists, none of it is claimed)

1. **A webhook receiver.** Verify the signature on the raw body before parsing (constant-time comparison, timestamp tolerance), reject anything unsigned, and keep the secret in hosting settings only.
2. **Record and apply in one transaction.** Today `record_event` and `save_subscription` are separate calls. If the process stops between them, the event is recorded as handled but its effect is lost for ever, because a retry is then ignored as a repeat.
3. **Ordering.** `save_subscription` replaces the stored state unconditionally. A late older event would overwrite a newer one. The subscription row needs the provider's event time (or version) and an event older than the stored one must be ignored.
4. **Status mapping** for trial and paused (decide what each gives, then test it).
5. **The organisation must come from the verified event** (a custom-data field the server set at checkout), never from anything the browser sent. Nothing may activate a plan from the checkout success redirect.
6. **Account deletion.** Deleting an account removes the workspace and, through the foreign key, its subscription row, without telling the provider, so a paying customer could keep being charged. Blocking deletion until the period ends would conflict with the right to erasure, so the safer design is: cancel at the provider first, abort deletion if that call fails, then delete. This needs the provider interface and is the pre-launch blocker already recorded as item 12 of the security checklist.
7. **Sandbox first.** Paddle stays in sandbox until the seller account is approved, products are configured, webhooks are tested and the whole lifecycle (create, upgrade, downgrade, cancel, renew, fail, refund) has been run end to end.

## Not verified here

Real Paddle behaviour (no sandbox account was used), tax and VAT treatment (owner decision), refunds and disputes (no handling exists), annual billing (not built) and load behaviour of the quota locks beyond the two concurrency tests, which need PostgreSQL to mean anything (CI runs them there).

## Statuses for this phase

- Local development: READY.
- Owned or authorised sites on the free plan: READY WITH CONDITIONS (see the security audit).
- Controlled pilot with free plans: READY WITH CONDITIONS; no billing is involved.
- Taking real payments: **NOT READY** until the seven items above exist and have been tested in the Paddle sandbox.
