# Developer experience audit

Phase 6 of the product-quality brief. Labels: **Verified** (code, tests), **Risk**, **Recommendation**, **Not tested**.

## What a developer gets today

- **API tokens for CI** (Professional and Agency plans): created under Integrations, shown once, stored as a hash, revocable, tied to the person who made them and limited to starting and reading scans of verified sites (`api/v1/ci.py`, `test_integrations.py`, `test_token_scope.py`).
- **GitHub Action** (`action/`, tag `v1`): inputs `api-key`, `url`, `min-score`, `fail-on`, `timeout-minutes`; outputs `scan-id`, `score`, `grade`, `passed`; distinct exit codes (0 rules met, 1 rules not met, 2 could not run). A scan that did not complete is never a pass. The token is masked, passed through a config file on stdin, and text from the scanned site is cleaned before it reaches the log or job summary. Connection errors and 502 to 504 are retried to survive cold starts.
- **Score badges** (opt-in, random address).
- **API reference:** `docs/API.md` and `docs/INTEGRATIONS.md`.

## Defects found and fixed

1. **CI results ignored triage.** `GET /ci/scans/{id}` listed every finding, including those the team had marked false positive or accepted risk, so `fail-on` could fail a pipeline on something already decided and the team had no way to unblock it. The answer now lists open findings only, with counts recomputed from them. Test: `test_ci_results_leave_out_findings_the_team_triaged` (it failed before the fix). The score is still the one worked out at scan time; this is stated in `INTEGRATIONS.md`.
2. **API documentation had fallen behind.** 22 of the 74 routes were not described in `API.md` (agency, schedules, shared reports, webhook update/test/rotate, analytics, OAuth sign-in, resend verification, platform health), and the page still said schedules were not implemented. Added them. A new test (`test_api_docs_cover_routes.py`) fails whenever a route is added without being documented; it fails against the old document.

## Risks and recommendations

| # | Finding | Type |
|---|---|---|
| 1 | Only Professional and Agency plans can create tokens, so a free-plan developer cannot try the Action. Paid plans are not live yet, so today nobody outside the operator can. Consider a limited free allowance when pricing is decided. | Product decision |
| 2 | The interactive API schema is off in production on purpose (it loads scripts from a public CDN). There is no public, hosted API reference page other than the Markdown files in the repository. | Recommendation (queued: public documented API) |
| 3 | The API has no version policy or changelog; routes live under `/api/v1` with no stated stability promise. The CI endpoints are the only ones intended for outside use. | Recommendation |
| 4 | 429 responses carry a message but no `Retry-After` header, so scripts must guess when to retry. The Action already retries the cases it cares about. | Recommendation (small) |
| 5 | The Action tag `v1` is moved by hand. Tagged releases and a changelog are in the queue. | Recommendation |
| 6 | The Action has not been tried from a real GitHub workflow with a real token on the live site. | Not tested |
| 7 | `docs/API.md` is a hand-written table; the new test checks that routes are listed, not that each description is correct. | Limitation |
