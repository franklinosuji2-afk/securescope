# Monitoring and alerting audit

Phase 3 of the product-quality brief. Labels: **Verified** (code or tests), **Risk**, **Recommendation**, **Not tested**.

## How monitoring works

- **Scheduled scans** run only from the cron endpoint, never from a browser. Each due schedule goes through the same checks as a manual scan: the site must still be verified, the address is validated again, and the scan uses the workspace's monthly allowance. At most 3 jobs run per cron call (`MAX_JOBS_PER_RUN`). (Verified: `services/scheduler.py`, `test_schedule_authorisation.py`.)
- **Alert emails** are sent when something got worse: a new finding that is not informational, a score drop of 5 points or more, or a failed scan. An unchanged result sends nothing. Recipients are owners, admins and security analysts of the workspace only. (Verified: `services/alerts.py`.)
- **Webhooks** (generic and Slack) retry on HTTP 5xx and 429 with a fixed delay and a bounded number of attempts; other failures are not retried. Deliveries are recorded. (Verified: `services/webhooks.py`.)

## Defect found and fixed: comparing scans when a check did not run

`compare_scans` treated a finding that is missing from the newer scan as resolved, and a finding missing from the older scan as new. When a check could not be evaluated (for example DNS did not answer), its findings vanish from that scan without being fixed. The per-site finding state already protected against this (`unverified_prefixes`), but the compare view and the alert logic did not.

- **Now:** findings whose check was skipped in either scan are put in a separate `not_comparable_findings` list, with the names of the checks that did not run. They are not counted as new or resolved, and the Compare page shows them in a "Cannot be compared" group with an explanation.
- **Effect on alerts:** a "new" finding from a check that was skipped last time no longer triggers an alert. That avoids a false alert but also means a real new finding of that kind is not announced until two scans have both run the check. Trade-off accepted; it is stated here and in the UI.
- Tests: 4 backend (`test_compare_csv.py`) and 2 frontend (`compare.test.tsx`).

## Risks and recommendations

| # | Finding | Type |
|---|---|---|
| 1 | Alerts are fire-once: if the email or webhook fails, nothing re-sends it on the next run. The webhook retry covers a failed POST, not a lost run. | Risk (already P1/P2 in the release-readiness report) |
| 2 | Scheduled runs depend on an external cron calling the endpoint. If that cron stops, scans silently stop; the Overview does not warn that a schedule is overdue. | Risk |
| 3 | The 3-jobs-per-call cap means a large number of due schedules is spread over several cron calls; with a slow cron interval, late scans are possible. | Risk (only at many sites) |
| 4 | Score-drop threshold (5) and the "informational notes never alert" rule are fixed, not per-workspace settings. | Recommendation |
| 5 | Add an "overdue schedule" indicator (next run in the past by more than one interval) on the Targets page and Overview. | Recommendation |
| 6 | The first real alert email, webhook and Slack message have not been checked end to end on the live site. | Not tested |
