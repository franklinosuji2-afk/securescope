# Domain verification audit

Date: 25 Oct 2026. Scope: the DNS TXT and HTTP-file ownership proof that authorises a scan. Written **before** any code change, from the code in `security/ownership.py`, `security/target.py`, `repositories/targets.py`, `api/v1/targets.py`, `models/target.py`, `pages/Targets.tsx` and the existing tests. Nothing was run against live DNS or production data.

Legend: PASS = correct and tested. PARTIAL = works, with a gap. FAIL = does not meet the requirement. NOT APPLICABLE = the feature does not exist.

## Findings

| # | Area | Verdict | Evidence | Risk / action |
|---|---|---|---|---|
| 1 | Hostname validation and canonical form | PASS | `normalize_hostname`: lower-case, trailing dot removed, IDNA to punycode, rejects IP literals, ports, paths, credentials, single labels, `localhost` and internal suffixes, labels over 63 characters, total over 253. Tested in `test_targets.py` (accept and reject tables) | None |
| 2 | Token generation | PASS | `secrets.token_hex(16)` (128 bits), new per target and per regeneration | None |
| 3 | Token bound to host and workspace | PASS | The token lives on the target row, which is unique per `(organization_id, hostname)`. The DNS name contains the host. A record for another host or another workspace's token does not match | None |
| 4 | Token stored as a hash | NOT APPLICABLE (by design) | The value must be shown to the owner so they can publish it, and it is public once published. A hash could not be redisplayed | Documented. Instead: shorten how long it is kept (rows 9 to 11) |
| 5 | DNS record format | PASS | `_securescope-challenge.<host>`, value `securescope-verification=<token>`; the UI shows name, type and value | Copy buttons are missing (row 18) |
| 6 | TXT parsing | PASS | Segmented strings are joined; several records at the name are accepted if any one equals the value exactly after trimming; apex and other labels are not read | None |
| 7 | Result distinction | PASS | Not found, mismatch, DNS failure or timeout (5 s lifetime), expired (409), rate limited (429) all have separate messages; a DNS error never marks the target verified | None |
| 8 | HTTP file check | PASS | Uses the SSRF-hardened fetcher; redirect to another host does not count; 512-byte cap; exact content | None |
| 9 | Expiry of an unverified challenge | PARTIAL | 7 days; the verify route refuses an expired challenge. **The expired token stays in the database and is still returned by the API and shown in the UI** | Minimum-data gap. Clear it |
| 10 | Token after successful verification | **FAIL** | `record_check` sets `verified_at` and leaves `challenge_token` in place. The API keeps returning it for a verified target | The brief and the owner ask for the challenge to be removed once verified. Clear it |
| 11 | Removing a challenge without deleting the site | **FAIL** | Only "New challenge" (replace) or delete the whole site | Add a "remove challenge" action |
| 12 | Regeneration invalidates the old token | PASS | Token replaced in place; `test_challenge_regeneration_invalidates_the_old_token` | None |
| 13 | Regeneration rate limit | PARTIAL | None on `/challenge`. Low risk (authenticated, manage role, workspace-scoped) but it is an unbounded write | Share the verify limiter budget |
| 14 | Race: regenerate or clear while a check runs | **FAIL** | `verify_target` reads the token, awaits DNS or HTTP (up to several seconds), then `record_check` marks verified without checking that the token is still the one that was checked. A challenge replaced or removed in that window can still verify | Make the success update conditional on the checked token |
| 15 | Authorisation | PASS | Every route uses `require(Permission.TARGET_READ/MANAGE)`; the repository takes the organization id on every call; cross-workspace access returns 404; role matrix tested (`test_other_organizations_cannot_see_or_touch_a_target`, `test_role_matrix_for_targets`) | None |
| 16 | Verify rate limit | PASS (with note) | 10 per target per hour (`target_verifications_per_target_per_hour`), counted per attempt. The limiter is in memory, so the limit is per instance | Note only; one instance today |
| 17 | Re-verification after the proof lapses (180 days) | PASS | A new challenge issued after the lapse is required; tested in `test_verification_expiry.py` | None |
| 18 | UI | PARTIAL | Shows name, type, value, expiry, verify and retry buttons. **No reassurance text, no copy buttons, and an expired challenge still shows its value** | Add the reassurance, hide expired values |
| 19 | Logging and privacy | PASS | Audit events carry ids only (`target.created`, `verified`, `verification_failed`, `challenge_regenerated`, `deleted`); no token in logs (searched). `last_check_error` holds fixed sentences | Add `target.challenge_removed` |
| 20 | Scanner integration | PASS | A scan needs `find_verified`, which needs status `verified`; the scanner keeps validate-then-connect. Unchanged | None |

## Summary of what will change

1. Clear the token and its expiry when verification succeeds (row 10).
2. Hide and delete expired tokens: the API stops returning an expired value, and the daily maintenance step erases the stored token once its expiry has passed (rows 9, 10).
3. A "Remove challenge" action that clears the token on any target (row 11).
4. A successful check only counts if the token is still the one that was checked (row 14).
5. Regeneration shares the verify rate limit (row 13).
6. The reassurance text and "No active challenge" wording in the UI (row 18).

Not changed: hashing (row 4, by design), the in-memory limiter (row 16), copy buttons (cosmetic; queued).

## Statuses

- Local development: READY.
- Owned or authorised sites: READY.
- Controlled external pilot: READY WITH CONDITIONS (conditions: the fixes above are deployed; the limiter is per instance).
