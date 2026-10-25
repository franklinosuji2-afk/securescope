# Domain verification: test evidence

Date: 25 Oct 2026. Everything below was executed locally (SQLite or a local PostgreSQL 16, mocked DNS and HTTP). No live DNS, production data or production migration was touched.

## Results

| Check | Result |
|---|---|
| Backend, full suite | 1046 tests, all passed (the new file adds 12) |
| Frontend (vitest) | 233 tests, all passed (3 new) |
| `ruff check app alembic`, `mypy app` (182 files) | Clean |
| Frontend lint, typecheck, format check, build | Clean; main bundle 371 kB |
| Secret scan | No secrets found |
| Migration `0019`: up, down to `0018`, up again | Passed on SQLite and on PostgreSQL 16 |
| Playwright browser tests | **Not run here** (they run only in CI) |

## New tests (`app/tests/test_domain_verification.py`)

| Test | What it proves |
|---|---|
| success erases the challenge | After a successful check the API returns no token or record value, and the stored token and expiry are `NULL` |
| a failed check keeps the challenge | A wrong or missing record does not erase the value |
| expired challenge hidden and purged | An expired value is not returned; `purge_expired_challenges` erases exactly the expired rows, leaves live ones, and is idempotent; a new challenge can be issued after |
| removing a challenge | `DELETE …/challenge` empties the values, blocks verification with 409 without any DNS lookup, writes `target.challenge_removed`, and a new challenge verifies normally |
| removing on a verified site | The site stays verified |
| lapsed proof with no challenge | 409 asking for a new challenge; a fresh one renews |
| challenge changed during a check (regenerate, remove) | The old value that was published cannot verify the domain; nothing is marked verified |
| other workspace | Cannot remove another workspace's challenge (404); the challenge is unchanged |
| role and session | A viewer gets 403; no session gets 401/403 |
| new-challenge rate limit | The third request in an hour gets 429; the budget is separate from verification attempts |
| no token in logs | The value does not appear in captured logs at DEBUG during create and verify |

Existing tests that already cover the rest of the brief: hostname canonicalisation and rejection (`test_targets.py`), exact record match and wrong label (`test_dns_txt_verification_succeeds_only_with_the_exact_challenge`), DNS failure not marking verified, expired challenge refused, regeneration invalidating the old value, per-target rate limit, HTTP file checks including a redirect to another host, SSRF-hardened fetch, cross-organization isolation and the role matrix (`test_targets.py`, `test_cross_customer.py`), proof lapse and renewal (`test_verification_expiry.py`), scans requiring a verified target.

Updated: `test_cross_customer.py` now attacks the new route; `test_route_coverage.py` (unchanged) is what forced that; `test_maintenance_loop.py` fake state has the new step; the `trust_host` helper passes the checked token.

## Mutation checks

Each change below was made by hand to the production code, the tests were run, and the code was restored.

| Mutation | Caught by |
|---|---|
| Keep the token after a success | `test_success_erases_the_challenge` |
| Remove the "is this still the checked token" comparison | both `challenge_changed_during_a_check` cases |
| Return a token even after it expired | the expired-challenge test and the existing `test_expired_challenges_cannot_be_used` |

## Not tested here

- Real DNS propagation, real resolvers, and a DNS provider returning odd records (the lookup is mocked; `system_txt_lookup` error mapping has its own existing test).
- Behaviour with two server instances (the limiter is in memory).
- The browser rendering of the new text and button (covered by vitest only, not by a browser run).
