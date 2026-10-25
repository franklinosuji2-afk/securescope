# Security remediation plan

## Completed in this audit

| Item | Change | Tests |
|---|---|---|
| F1 | Start-up refuses CORS wildcards, `null` and empty origins | `test_config_guards.py` |
| F2 | Start-up refuses the placeholder database password on an https deployment | `test_config_guards.py` |

Both are small configuration guards. No authentication, authorisation, ownership, SSRF or subscription control was changed or relaxed, and no test was deleted.

## Outstanding work (can be done without owner approval)

| Priority | Work |
|---|---|
| P3 | Idle timeout for sessions; `__Host-` cookie prefix; pin GitHub Actions to commit hashes (Dependabot can then update them) |
| P3 | Optional: list unused endpoints and packages and remove them one at a time |

## Needs explicit owner approval or action

| Priority | Action | Who |
|---|---|---|
| Before paid launch | Cancel or block account deletion while a paid subscription is live; build and test payment webhook verification, ordering and duplicate handling | Owner decision, then development |
| P2 | Separate migration and runtime database roles | Hosting change |
| P2 | Cloudflare edge rate-limit rule | Cloudflare dashboard |
| P2 | Run `scripts/backup-db.ps1` and `scripts/restore-test.ps1` once and record the date in `docs/OPERATIONS.md` | Owner's PC |
| P2 | Confirm GitHub branch protection, required status checks and secret scanning with push protection | GitHub settings |
| Owner | Check `SECURESCOPE_CORS_ORIGINS` has no wildcard before deploying this change | Hosting dashboard |
| Owner | Delete local secret files; rotate anything ever pasted into a chat | Owner |

Nothing was deployed, committed to the remote, rotated or migrated by this audit.
