# Security remediation plan

## Completed in this audit

| Item | Change | Tests |
|---|---|---|
| F1 | Start-up refuses CORS wildcards, `null` and empty origins | `test_config_guards.py` |
| F2 | Start-up refuses the placeholder database password on an https deployment (case-insensitive) | `test_config_guards.py` |
| F3 | CORS origins must be exact (no path, trailing slash, upper case) | `test_config_guards.py` |
| F4 | Validation errors no longer echo the rejected input | `test_error_responses.py` |
| F5 | Removed unused `charset-normalizer` pin | Full suite in a clean environment |

Both are small configuration guards. No authentication, authorisation, ownership, SSRF or subscription control was changed or relaxed, and no test was deleted.

## Outstanding work (can be done without owner approval)

| Priority | Work |
|---|---|
| P3 | Idle timeout for sessions; `__Host-` cookie prefix; pin GitHub Actions to commit hashes (Dependabot can then update them) |

## Needs explicit owner approval or action

| Priority | Action | Who |
|---|---|---|
| Before paid launch | Cancel or block account deletion while a paid subscription is live; build and test payment webhook verification, ordering and duplicate handling | Owner decision, then development |
| P2 | Separate migration and runtime database roles | Hosting change |
| P2 | Cloudflare edge rate-limit rule (blocked on the free plan: its one slot is the leaked-credential check) | Cloudflare plan decision |
| P2 | Backups run and a restore passed on 23 and 25 Oct. Remaining: a regular schedule | Owner |
| P2 | Confirm GitHub branch protection, required status checks and secret scanning with push protection | GitHub settings |
| Owner | Before deploying: `SECURESCOPE_CORS_ORIGINS` must be a JSON list of exact origins (no trailing slash, no upper case, no wildcard) and `SECURESCOPE_DATABASE_URL` must not contain `change-me`, or the service refuses to start | Hosting dashboard |
| Owner | Delete local secret files; rotate anything ever pasted into a chat | Owner |

Nothing was deployed, committed to the remote, rotated or migrated by this audit.
