# Security test evidence

Commands actually run on 25 Oct 2026 against the code that contains this file, with their results. Local database: PostgreSQL 16; CI uses 18. Playwright (browser) tests were not run locally. In CI, the e2e job succeeded on commit `20b0f7b` (the last one pushed) together with frontend, backend, security and docker; later commits are not yet pushed. ruff, mypy and bandit were clean.

## Test suites

| Command (from `backend/` unless stated) | Result |
|---|---|
| `pytest -p no:cacheprovider -q -W ignore` (full suite, Postgres) | 1,012 passed, 0 failed (closure review, clean environment without `charset-normalizer`) |
| `pytest app/tests/test_config_guards.py app/tests/test_target.py` | passed |
| `npx vitest run` (from `frontend/`) | 222 tests passed |

## Static analysis and audits

| Command | Result |
|---|---|
| `ruff check app alembic` | All checks passed |
| `mypy app` | Success: no issues found in 172 source files |
| `bandit -q -r app -x app/tests` | exit 0, no issues reported |
| `pip-audit -r requirements.txt` | No known vulnerabilities found |
| `npm audit --omit=dev` (from `frontend/`) | found 0 vulnerabilities |
| `npm run lint`, `npm run typecheck`, `npm run format:check` | all clean |
| `python3 scripts/scan_secrets.py --history` | No secrets found in files or history |
| Search of `frontend/dist` for source-map references and secret-shaped strings | none found |

## Mutation checks (isolated copy of the code, each restored with `git checkout` afterwards)

| Weakened control | Tests run | Tests that failed | Baseline |
|---|---|---|---|
| CSRF check replaced by `if False:` (`api/deps.py`) | `test_auth`, `test_scan_control` | 2 | 0 failed |
| `is_public_address` returns True for everything (`security/target.py`) | `test_ssrf_matrix`, `test_target` | 72 | 0 failed |
| Session revocation ignored (`repositories/accounts.py`) | `test_auth`, `test_cross_customer` | 3 | 0 failed |
| `CanShare` weakened (earlier verification, `SECURITY_VERIFICATION.md`) | `test_agency_roles` | failed as expected | passed |

After each mutation the working tree was confirmed clean.

## Security-specific test files

`test_cross_customer`, `test_route_coverage`, `test_authentication_sweep`, `test_agency_roles`, `test_token_scope`, `test_schedule_authorisation`, `test_ssrf_matrix`, `test_fetcher`, `test_deletion_sweep`, `test_account_deletion_data`, `test_subscription_invariants`, `test_plans`, `test_log_secrets`, `test_auth`, `test_scan_control`, `test_config_guards`, `test_error_responses` (new).

## Not run

Live-site penetration testing, load testing, real DNS-rebinding against live resolvers, the live mail and webhook paths, and anything on the production host or database.
