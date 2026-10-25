# Agency and freelancer workflow audit

Phase 5 of the product-quality brief. Labels: **Verified** (code or tests), **Risk**, **Recommendation**, **Not tested**.

## What exists today

- **Client workspaces:** create, rename and delete clients; assign each verified site to one client; a dashboard per client with sites, open findings by severity, worst grade and last scan (`api/v1/agency.py`, `pages/Clients.tsx`). Plan-gated: a free plan gets 403 (`test_agency_roles.py`).
- **Roles:** owner, admin, security analyst and read-only roles, checked on the server for every agency endpoint against a matrix (`test_agency_roles.py`). Roles apply to the whole workspace.
- **Shared reports:** a link per completed scan, valid for a chosen number of days, shown once and stored only as a hash, revocable, rate-limited, audited (`share.created`, `share.revoked`). The report is rendered when the link is created, so it is a snapshot (Verified: `create_share`).
- **Branding:** the agency name on reports. No logo, colours or custom domain.
- **Isolation:** every agency id (client, share, member, invitation) is attacked from another customer in `test_cross_customer.py`.

## Verified

- A free workspace cannot use agency endpoints; a removed member and a non-member are refused.
- Expired, revoked, unknown and malformed share links all get the same refusal; deleting a scan deletes its links; client details and notes never reach a shared or downloaded report (`test_agency.py`).
- Deleting a client leaves its sites and scans in the workspace, unassigned (`repositories/agency.py::delete_client`); they appear under "Not assigned to a client" on the dashboard.

## Gaps

| # | Finding | Type |
|---|---|---|
| 1 | No client-level report: an agency sends one PDF per site, not one summary per client. | Recommendation (queued project: agency client-level reports) |
| 2 | No scheduled report emails to a client contact. Alerts go to workspace members only, by design. | Recommendation (queued) |
| 3 | No per-client permissions: a member sees every client in the workspace. | Risk for agencies that need to separate staff; already in the roadmap (Phase 8) |
| 4 | Branding is a name only. No logo, so reports look like SecureScope reports with a different name. | Recommendation |
| 5 | No bulk assign: sites are moved to a client one by one. Fine at the 20-site cap of the largest paid plan. | Recommendation (minor) |
| 6 | The dashboard reads at most 200 sites and loads each site's latest scan separately; `total_sites` counts the sites it read, not all of them. Unreachable on paid plans (20 sites), possible only on the operator's unlimited internal plan. | Risk (P3), not changed |
| 7 | Shared links are bearer links: anyone holding one can read that report until it expires or is revoked. The expiry choices and revoke button are the controls; the UI should keep stating this. | Documented |
| 8 | The live agency screens were not exercised: the signed-in account is not on an agency plan, and paid plans are "Coming soon" until Paddle approves. | Not tested |

## Recommendation order

1. Client-level report (one PDF per client, listing each site's score and open findings), then scheduled report email to a client contact. Both build on existing report and share code.
2. Logo in branding (needs an upload design and review, since the app accepts no uploads today).
3. Per-client permissions, as part of the subscription and roles work.

No application code was changed in this batch.
