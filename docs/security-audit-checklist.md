# Security audit checklist

Audit date: 25 Oct 2026. Scope: the SecureScope repository at the commit that contains this file. Every item was checked against the code, configuration and tests, not against the existence of a test alone. Statuses follow the audit brief: PASS, PARTIAL, FAIL, NOT VERIFIED, NOT APPLICABLE.

**Totals (after the closure review of 25 Oct 2026):** PASS 54, PARTIAL 6, FAIL 0, NOT VERIFIED 2, NOT APPLICABLE 6 (68 items). Items 39 and 57 moved from NOT VERIFIED to PASS; items 19 and 41 stay PASS with corrected evidence. See the closure section at the end.

Items 14 and 36 were PARTIAL when first inspected and are PASS after the small fixes made in this audit (see [security-findings.md](security-findings.md)).

Columns: status; evidence (files, routes, tests); risk and remediation, including whether a change is required; verification test; limitation of the assessment. Test commands and results are in [security-test-evidence.md](security-test-evidence.md).

| # | Control | Status | Evidence | Risk, remediation, change required | Verification test | Limitation |
|---|---|---|---|---|---|---|
| 1 | Protect administrative routes | **PASS** | `test_authentication_sweep.py` (every route 401 except a 15-route public allow-list); cron endpoint needs a 32+ character secret; `/metrics` needs a bearer token and is 404 without one | None | `test_authentication_sweep`, `test_platform_health` | No separate admin UI exists; operator routes are the cron and metrics endpoints |
| 2 | Server-side permissions | **PASS** | `security/permissions.py` role matrix; `test_agency_roles.py` runs every agency endpoint x 5 roles against the matrix; mutation check on `CanShare` made it fail | None | `test_agency_roles`, `test_token_scope` | Roles are workspace-wide (no per-client permissions) |
| 3 | Users reach only their own and authorised workspace data | **PASS** | `test_cross_customer.py` attacks every id-taking route with another customer's ids; `test_route_coverage.py` fails when a new id route is not covered | None | `test_cross_customer`, `test_route_coverage` | Tests use two synthetic customers on one database |
| 4 | Row-level security | **NOT APPLICABLE** | Tenancy is enforced in the application (organisation id on every query) over one database role. RLS would only add protection with a per-request database role or session setting, which this architecture does not use | Not adopted deliberately; adding RLS blindly would not change who can read what. Revisit if a second service ever connects to the database | n/a | Defence in depth would need a different connection model |
| 5 | Verified email before verified-owner features | **PASS** | `require_verified_email` defaults to true; enforced in `api/deps.py`; tests in `test_auth.py` and `test_client_accounts.py` | None | `test_client_accounts` | Depends on the live mail provider delivering (release-readiness P1-4) |
| 6 | Password hashing | **PASS** | Argon2id via argon2-cffi defaults, length 12 to 128, dummy-hash verification so missing accounts take the same time, rehash on login (`services/auth.py`) | None | `test_auth` | Timing equality is by design, not measured |
| 7 | Tokens not in insecure browser storage | **PASS** | Session is an HttpOnly cookie; the only browser storage is theme (localStorage) and the workspace id and a pending invitation token (sessionStorage); no auth token | The pending invitation token in sessionStorage is short-lived and single-use; acceptable | grep of `frontend/src` | Static review only |
| 8 | Session expiry, logout, revocation, cookie security | **PASS** | 12 h TTL; logout revokes the session, a password reset revokes all sessions, a password change revokes the other sessions; cookie HttpOnly, SameSite=Lax, Secure by default; revoked sessions rejected. Mutation: ignoring revocation fails 3 tests | P3: no idle timeout and no `__Host-` cookie prefix. Not changed | `test_auth` (replay of a revoked cookie) | Cookie flags checked in code and tests, not on the wire |
| 9 | API tokens follow the same rules as sessions | **PASS** | `test_token_scope.py`: a token gets the anonymous answer on every non-CI route; a token whose owner is demoted gets 401 | None | `test_token_scope` | CI routes only; no broader API-token surface exists |
| 10 | Access control on reports, histories, exports, teams, agency, jobs | **PASS** | Covered by `test_cross_customer` (reports, exports, shares, clients, invitations, sessions), `test_agency_roles`, `test_schedule_authorisation` | None | same | Shared-report links are bearer links by design |
| 11 | Removed members, expired permissions, membership changes | **PASS** | `test_agency_roles` covers a non-member, a removed member and a free plan; invitations expire | None | `test_agency_roles`, `test_invitations` | No time-limited roles exist, so none to expire |
| 12 | Account deletion and data export respect ownership | **PARTIAL** | `GET /account/export` returns only the signed-in user's data; deletion sweep removes all user rows (`test_deletion_sweep.py`) | Deleting an account does not cancel a live paid subscription. No paid plans are live yet, so no user is affected today; must be fixed before Paddle (release-readiness P1-2). Needs owner decision | `test_deletion_sweep`, `test_account_deletion_data` | Billing provider integration does not exist yet; the deletion design is in [subscription-readiness-audit.md](subscription-readiness-audit.md) |
| 13 | Secrets stay on the server | **PASS** | Settings use `SecretStr`; built bundle has no secret-shaped strings | None | Bundle grep of `frontend/dist` | Pattern based |
| 14 | Environment handling fails safely | **PASS** | Start-up validators refuse short cron/webhook secrets, incomplete mail config, private-target mode with secure cookies. New: refuses CORS wildcards and a placeholder database password on an https address | Fixed in this audit | `test_config_guards`, `test_target` | Cannot see the host's real environment variables |
| 15 | .env and credentials not committed | **PASS** | `.gitignore` covers `.env*`; `git ls-files` lists only `.env.example` | None | `git ls-files` search | Tracked files only |
| 16 | Git history scanned for secrets | **PASS** | `scripts/scan_secrets.py --history` clean; also runs in CI | None | Command in test-evidence | Regex scanner, not an entropy scanner; GitHub push protection also active |
| 17 | Exposed secrets needing owner-approved rotation | **NOT VERIFIED** | No secret found in the repository or history. On 25 Oct the owner deleted the Google sign-in client file from Downloads and an old unrelated `.env`, and checked that the portfolio repository's history has none. Not rotated: the owner states the Google secret was never pasted or shared | Owner statement only; Claude cannot inspect the PC or the hosting dashboards. Rotate the Google secret if that statement is wrong | n/a | Cannot inspect the owner's PC or hosting dashboards |
| 18 | Logs and errors contain no credentials or personal data | **PASS** | `test_log_secrets.py`; JSON logger fields are explicit; webhook secrets never logged | None | `test_log_secrets` | Third-party logs (host, Cloudflare) not reviewed |
| 19 | Debug off, verbose errors off in production | **PASS** | No reload flag in the container command; API docs off by default; unhandled errors return a generic 500; tracebacks are logged server-side only | None | `test_error_responses` (500 body has no marker, traceback or exception name); `test_platform_health` covers only the status code and metric | Real production environment not inspected |
| 20 | No secrets in bundles, source maps or public config | **PASS** | No source maps in `dist`; no secret-shaped strings; `frontend/public` holds static files only | None | Command in test-evidence | Pattern based |
| 21 | Parameterised queries | **PASS** | SQLAlchemy ORM throughout; no raw SQL, `text()` or f-string SQL in `app/` | None | grep | Static review |
| 22 | Input validation | **PASS** | Pydantic request models with length limits; Query bounds; `validate_target` for URLs; 18 webhook URL tricks rejected (`test_ssrf_matrix`) | None | `test_ssrf_matrix`, `test_target` | No fuzzing performed |
| 23 | Output encoding / XSS | **PASS** | React escaping; no `dangerouslySetInnerHTML`; Jinja autoescape for HTML and PDF; Markdown escaping; hostile-evidence tests | None | `test_db_and_reports`, `test_pdf_report` | CSP on the static site allows inline styles |
| 24 | File uploads | **NOT APPLICABLE** | The application accepts no uploads (no `UploadFile`/multipart) | If uploads are added, they need a new review | n/a | n/a |
| 25 | SQL injection | **PASS** | See 21 | None | grep | Static review |
| 26 | Unsafe deserialisation, path traversal, command injection | **PASS** | No pickle, yaml.load, eval/exec, subprocess or shell use; the only file paths are fixed package paths | None | grep | Static review |
| 27 | Database credentials least privilege | **PARTIAL** | The container runs migrations at start-up (`python -m app.database.migrate`) under the same role as the application, so the runtime role can change the schema | Recommendation: a separate migration role and a runtime role with data access only. Needs hosting changes, so owner approval | n/a | Neon role grants cannot be read from the repository |
| 28 | Storage permissions | **NOT APPLICABLE** | No object storage or file storage is used; reports are generated on demand | n/a | n/a | n/a |
| 29 | Transactions and consistency for sensitive operations | **PASS** | Plan limits under concurrency (`test_plans.py`), subscription invariants over 7,000 combinations, deletion sweep | None | `test_plans`, `test_subscription_invariants` | Postgres-only tests; SQLite lacks the locking |
| 30 | RLS where applicable | **NOT APPLICABLE** | See 4 | See 4 | n/a | n/a |
| 31 | Every endpoint: auth, authorisation, validation, errors | **PASS** | Authentication sweep, route-coverage test and cross-customer attacks | None | same | Authorisation logic per endpoint was verified by tests, not each re-read |
| 32 | Webhook signatures | **NOT APPLICABLE** | Outbound webhooks are signed (HMAC-SHA256 over timestamp and body). No inbound webhook endpoint exists yet | Paddle webhook verification must be built and tested with the billing work | n/a | Inbound signature handling does not exist |
| 33 | Webhook replay protection and idempotency | **NOT APPLICABLE** | Outbound messages carry a timestamp. No inbound webhooks exist; scans accept an `Idempotency-Key` | Payment event ordering and duplicates are release-readiness P1-1 | n/a | Same as 32 |
| 34 | Rate limiting of sensitive operations | **PARTIAL** | Limiters exist for login, reset, resend, registration, token creation, scans, reports, shares, webhooks, cron, password change | Counters are in memory: reset on restart and not shared if more than one instance runs. The Cloudflare free plan has one rate-limiting rule and it is used by the leaked-credential check, so no edge rule was added on 25 Oct (a first custom block rule was removed before it affected anyone). Acceptable for one instance; revisit with a paid plan or shared store | `test_auth`, `test_scan_control` | Single-instance deployment assumed |
| 35 | HTTP security headers and browser policies | **PASS** | API: nosniff, DENY framing, no-referrer, CORP, CSP, no-store. Static site `_headers`: CSP, nosniff, DENY, referrer, permissions policy. SecureScope's own scan of its site reports informational findings only | None | Live scan history; `test_platform_health` | HSTS is set at the Cloudflare edge, not in the repository |
| 36 | CORS restrictive | **PASS** | Allow-list with credentials; unknown origins refused on unsafe methods. New: a wildcard, `null` or empty origin is refused at start-up | Fixed in this audit | `test_config_guards` | Existing tests cover the allow-list behaviour |
| 37 | Debug and development endpoints disabled | **PASS** | `api_docs_enabled` false by default; `allow_private_targets` cannot combine with secure cookies or an https address | None | `test_target` | Host environment not inspected |
| 38 | Dependency vulnerabilities | **PASS** | pip-audit: none; npm audit (production): none, on the audit date | None | Commands in test-evidence | Known advisories only; Dependabot opens weekly update PRs |
| 39 | Unused or exposed endpoints and dependencies | **PASS** | 72 of 74 routes are called by the frontend or the GitHub Action. The other two are `/ready` (Docker healthcheck) and `/auth/refresh` (authenticated, tested, not used by the UI). Every route is authenticated or on the public allow-list in `test_authentication_sweep` | None | `test_authentication_sweep` | Reference check by search, not by traffic |
| 40 | Badges, exports, report links, caches | **PASS** | Badge is opt-in, random address, shows only score and grade, rate-limited; API responses are no-store; service worker never touches `/api` | None | `test_cross_customer` (shares), badge tests | Share links are bearer links; anyone holding one can read that report |
| 41 | API errors reveal no internals | **PASS** | Generic 500 body; validation errors list `loc`, `msg` and `type` only. The closure review found that FastAPI's default 422 echoed the rejected input (including a weak password); a handler in `main.py` now removes it | None | `test_error_responses` | Not fuzzed |
| 42 | Cross-customer isolation for every resource and route | **PASS** | See 3 | None | `test_cross_customer` | See 3 |
| 43 | Agency roles and client boundaries | **PASS** | See 2; roles apply to the whole workspace | Per-client permissions are a product decision (Phase 8) | `test_agency_roles` | Not per client |
| 44 | API tokens cannot bypass plan limits or permissions | **PASS** | See 9; scans via tokens use the same limiter and allowance path | None | `test_token_scope`, `test_plans` | CI routes only |
| 45 | Scheduled scans need valid ownership and authorisation | **PASS** | `test_schedule_authorisation.py`: lapsed proof, tampered host, private IP, deleted target, exhausted allowance | None | same | Cron trigger secret is the single entry point |
| 46 | Ownership changes, expired verification and deleted sites stop scanning | **PASS** | Same tests plus verification-expiry tests | None | same | Same |
| 47 | Outbound requests use the safe path | **PASS** | Scanner, webhooks, OAuth and mail use `trust_env=False` and validated addresses | None | `test_fetcher`, `test_ssrf_matrix` | Static review of call sites |
| 48 | SSRF, DNS rebinding, redirects, private IPs, metadata | **PASS** | `test_ssrf_matrix`, `test_fetcher` (metadata address in DNS answers); mutation: treating every IP as public fails 72 tests | None | same | Real DNS rebinding timing not simulated against live resolvers |
| 49 | Webhook destinations cannot reach internal services | **PASS** | 18 URL tricks rejected with nothing stored; same address validation as the scanner | None | `test_ssrf_matrix` | Same |
| 50 | Account deletion removes user data, jobs, tokens, integrations | **PASS** | Schema-driven sweep of every reference to users and organisations; text search for the email, workspace name and webhook secret | None | `test_deletion_sweep` | Backups keep data until they expire (documented) |
| 51 | Entitlements enforced on the server | **PASS** | Plan resolved server-side; invariants over 7,000+ combinations | Operator-assigned plan vs lower subscription is an owner decision | `test_subscription_invariants`, `test_plans` | No live billing provider |
| 52 | Reports and job results unavailable to unauthorised users | **PASS** | See 10 | None | `test_cross_customer` | See 10 |
| 53 | Rate and resource limits against scan abuse | **PARTIAL** | Per-client and per-target limits, a concurrency semaphore, 3 scheduled jobs per cron call, a monthly allowance, and a global queue cap (`api/v1/scans.py` answers 429 when pending scans reach 4 times the concurrency limit) | In-memory counters (see 34); the queue cap is per instance | `test_scan_control` | Load test not run (queued project) |
| 54 | Tracked files scanned for secrets | **PASS** | Secret scan clean; only `.env.example` tracked | None | Command in test-evidence | Pattern based |
| 55 | Git history scanned | **PASS** | See 16 | None | same | Same |
| 56 | Dependency manifests and lockfiles | **PASS** | Backend pinned in `requirements.txt`; frontend `package-lock.json`; audits clean | None | Commands in test-evidence | Transitive packages not individually reviewed |
| 57 | Remove unused packages | **PASS** | `depcheck` found no unused npm packages. Every Python pin is imported or required by another package, except `charset-normalizer` (left over from the old PDF library), which was removed; the suite passes in a fresh environment without it | None | Full backend suite in a clean venv | Transitive packages are pip's choice |
| 58 | Production build settings | **PASS** | No source maps; no dev server in the container; docs off | None | `dist` inspection | Host settings not inspected |
| 59 | Database and storage least privilege | **PARTIAL** | See 27 | See 27 | n/a | See 27 |
| 60 | Backups and restore testing | **PARTIAL** | `scripts/backup-db.ps1` and `restore-test.ps1` exist; restore was tested against a real PostgreSQL 16 in development; the PowerShell scripts were run on the owner's PC against the production database on 23 and 25 Oct (restore passed, schema 0018, 28 tables; output seen by Claude) | No scheduled backup yet: the owner should take one at least weekly and before each migration | `docs/OPERATIONS.md` procedure | Backup access controls on the host not reviewed |
| 61 | CI permissions, secrets, triggers | **PASS** | Workflow permissions are read-only; triggers are push to main and pull_request (not pull_request_target); no secrets used; Dependabot enabled | P3: first-party actions are pinned to major tags, not commit hashes | Workflow review | GitHub repository settings not readable |
| 62 | Security-sensitive configuration cannot change silently | **NOT VERIFIED** | Start-up validators block dangerous combinations, and CI runs on every push. Branch protection could not be read (403). On 25 Oct the owner reported a ruleset blocking deletion and force pushes on `main` and secret scanning with push protection; required checks and reviews are deliberately off because the owner pushes directly | Owner-reported, not verified by Claude | n/a | Repository settings not accessible |
| 63 | Run existing security regression tests | **PASS** | Full backend suite, including all security tests | None | Commands in test-evidence | Postgres 16 locally; CI uses 18 |
| 64 | Run backend and frontend suites | **PASS** | Backend, vitest; Playwright runs in CI | None | Commands in test-evidence | Playwright run by CI only for this audit |
| 65 | Static analysis, linting, type checks, dependency audit | **PASS** | ruff, mypy, bandit, eslint, tsc, prettier, pip-audit, npm audit | None | Commands in test-evidence | Tools find known patterns only |
| 66 | Targeted tests for confirmed gaps | **PASS** | `test_config_guards.py` (4 cases) | None | `test_config_guards` | Only two gaps were confirmed |
| 67 | Tests fail when a control is weakened | **PASS** | Mutation checks: CSRF check removed (2 tests fail), every IP public (72 fail), revocation ignored (3 fail), earlier `CanShare` weakened (fails); clean baseline passes | None | Mutation procedure in test-evidence | Four controls mutated, not all |
| 68 | Final security review of changes and tests | **PASS** | Diff reviewed: config validators and tests only; no control weakened | None | `git diff` | Reviewed by the author of the change |

## Closure review (25 Oct 2026)

The earlier results were treated as unverified. Evidence found: the full backend suite passes in a clean environment built from `requirements.txt` without the removed pin; ruff, mypy (175 files) and bandit are clean; the frontend passes lint, types, formatting and 222 tests. The CI run for the last pushed commit (`20b0f7b`) shows frontend, backend, security, docker and e2e (Playwright) all successful against that same commit; the batch 9 and batch 10 commits had not been pushed when this was written, so their CI is outstanding.

### Fixes made in the closure review

| Change | Why |
|---|---|
| `core/config.py`: each CORS entry must be exactly `scheme://host[:port]`, lower case, no path, no trailing slash, no wildcard; an empty list is allowed; the `change-me` database check is case-insensitive | The first guard accepted a trailing slash, a path, upper case and `Change-Me`. The list must be JSON in the environment; plain or comma strings already fail closed |
| `main.py`: validation errors return `loc`, `msg` and `type` only | Default 422 echoed the rejected input, including a weak password (P3) |
| `requirements.txt`: removed unused `charset-normalizer` | Item 57 |
| Tests: extended `test_config_guards.py`; new `test_error_responses.py` | Cover the above |

Not covered by the guard: the placeholder password with a non-https `public_base_url`, and an installation with nothing configured (development defaults). Both are intended for local use.

### The six PARTIAL items

| # | Gap | Impact | Blocks a controlled pilot? | Smallest safe fix | Test needed |
|---|---|---|---|---|---|
| 12 | Deleting an account does not cancel a paid subscription | None while no paid plan is live | No. Blocks paid launch | Block or cancel at deletion once Paddle exists | Deletion with an active subscription |
| 27 / 59 | Migrations run under the runtime database role | A compromised application could change the schema | No, with a trusted pilot | Separate migration role (hosting change) | None in code |
| 34 | In-memory rate limiters | Reset on restart; not shared across instances | No on one instance, with the edge rule | Cloudflare rate-limit rule | None in code |
| 53 | Same limiters; queue cap is per instance | Same as 34 | No | Same as 34 | Load test (queued) |
| 60 | Backup and restore scripts not run on the owner's PC | Unproven recovery | Yes, as a condition: run once before real customer data | Run both scripts, record the date | None |

None is a confirmed code defect that blocks a pilot, so none was changed.

### NOT VERIFIED

- 17 (secret rotation): the secret files are on the owner's PC and the hosting dashboards are not accessible. Needs the owner.
- 62 (branch protection): the GitHub API refused the read (403). Needs the owner to confirm required status checks and secret scanning.

### Mutation tests

The CSRF test (`test_auth.py`), the revoked-session test and the SSRF matrix (`test_ssrf_matrix.py`) assert outcomes (403, rejected cookie, address refused), not implementation details. Existing coverage of other high-value controls (tenant isolation, authentication sweep, API token scopes) is outcome-based. No further test was added beyond the two above.

### Pilot readiness

| Scope | Status | Conditions |
|---|---|---|
| Local development | READY | None |
| Owned or authorised sites | READY WITH CONDITIONS | Ownership verification and authorisation confirmation are enforced and tested; scans of third-party sites stay off |
| Controlled external pilot (free plans) | READY WITH CONDITIONS | Restore test run (done 25 Oct); one Render instance, since the edge rate-limit rule was not added; branch protection owner-reported; production CORS and database URL checked against the stricter guards; batch 9 and 10 CI green |
| Public commercial launch | NOT READY | Subscription cancellation on deletion; payment webhooks; separate database roles; legal and VAT review |

Passing tests are not proof of complete security; no live penetration test, load test or review of the production host was done.
