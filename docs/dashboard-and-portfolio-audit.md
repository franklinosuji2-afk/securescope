# Dashboard and portfolio audit

Phase 2 of the product-quality brief. Labels: **Verified** (seen on the live site or in code/tests), **Risk**, **Recommendation**, **Not tested**.

## What was checked

- **Verified (live, signed-in, read-only):** the Overview at `getsecurescope.com` with two verified sites (`cfo-dev.pages.dev`, `getsecurescope.com`). It shows verified-site count, open findings (6), critical/high (0), lowest score (100), the weakest site with score history, a top open issue per site, scan activity, site inventory, and per-site report downloads. No scan was started and no form was submitted.
- **Verified (code):** `ScanRepository.overview` and `BentoGrid`.

## Verified behaviour

- Only completed scans count; failed and unfinished scans are ignored. Resolved, accepted and false-positive findings are not counted as open.
- **Partial coverage is disclosed.** The overview lists at most 6 recently scanned sites. When more sites have been scanned, the score card says "Lowest score among the N most recently scanned sites (M scanned)", and inventory rows for unlisted sites say "scanned, not among the sites listed here". Totals are therefore never presented as covering sites they do not cover.
- Scan history is paged (`limit`/`offset`, "load more"), and since batch 1 costs the same number of queries for a large page as a small one.
- The score card carries the standing caveat that a high score is a heuristic, not proof of security.
- The empty state ("No sites added yet", "Nothing needs action right now. This does not mean your sites are secure.") makes no claim it cannot support.

## Gaps for a portfolio of many sites

| # | Finding | Type |
|---|---|---|
| 1 | The site inventory shows 6 of N and the Targets page lists every site with no search, sort or status filter. Fine at a handful of sites; slow to use at 30+. | Risk (agency use) |
| 2 | The overview does not show the next scheduled scan per site; `next_run_at` exists on schedules but is only shown on the Targets page. | Recommendation |
| 3 | With a tie (both sites 100) the card says "Lowest-scoring site" and names one arbitrarily. Accurate but could read as a ranking. Suggested wording when all listed scores are equal: "All listed sites score 100". | Recommendation (copy) |
| 4 | The 6-site overview window is fixed. Totals beyond it are available only by opening each site or History. | Risk (documented, disclosed) |
| 5 | No sorting of the inventory by score, open findings, or last scan, so "which site needs attention first" is answered only by the single top finding. | Recommendation |
| 6 | Portfolio behaviour above 6 sites is covered by unit tests (`bento.test.tsx`) but **was not exercised live**: the account has two sites. | Not tested |

## Recommendations, in order

1. Targets page: add a text filter and a "needs attention" sort (unverified, expired, lowest score, oldest scan). Frontend only, no API change needed while the plan caps the number of sites.
2. Overview: show "Next scan" under each site when a schedule exists.
3. Tie copy for the weakest-site card (item 3).

None of these is a correctness or security problem, so no application code was changed in this batch.
