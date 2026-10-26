# Performance and maintainability review

Date: 25 Oct 2026. Section 17 of the product-quality brief. Every item below was checked in the code first; a change was made only where there was evidence. **No caching, queue, index or paid infrastructure was added.** There is no production load data (the service has had no external users), so "evidence" here means code paths whose cost grows with data, and the size of what visitors download.

## Result

| Check from the brief | Finding | Action |
|---|---|---|
| N+1 queries | Scan list loads findings with one extra query per page (`selectinload`). Overview loads the latest scan's findings once per listed site (at most six sites). | None needed |
| Full-table queries | **Agency dashboard: `latest_completed_scans` loaded every completed scan of every listed site and picked the newest in Python.** | **Fixed** |
| Unbounded history loading | The same query. Everything else is bounded: scan list (max 100 per page), overview (500-scan window), finding state (about 40 rules per site), feedback summary (20 entries). | Fixed above |
| Missing pagination | Scans and audit events are paged with a cap. Targets, schedules, tokens and clients are listed whole, but each is capped by the plan's limits (websites, tokens). | None needed |
| Duplicate frontend requests | None found in the pages read. | None |
| Excessive polling | A running scan is polled every 1.2 s until it finishes; Platform Health every 30 s while the operator has it open; the update check every 15 minutes and only while the tab is visible. | Documented; reasonable at this scale |
| Expensive report generation in a request | PDF building is off the event loop, limited to one at a time, rate limited per user, stored after the first build and checked by checksum on download. | None; this is already well done |
| Unbounded job retries | Scheduled scans are claimed once with a compare-and-set update (at most three per call); a failed scan is not retried by itself; hourly clean-up now survives a failed step (Phase 9). | None |
| Slow dashboard aggregation | Overview and agency dashboard are bounded as above. Platform Health reads the completed scans of the last 24 hours across all workspaces to average their duration. | Documented (see below) |
| Missing indexes | Every demonstrated filter has one: scans by workspace and time, findings by scan, finding state by workspace and host, audit by workspace and time, schedules by next run, page views by time. | None |
| Excessive frontend bundle | **One 498 kB file (145 kB compressed) was downloaded by every visitor, including those who only see the home page.** | **Fixed** |
| Unnecessary dependencies | `charset-normalizer` was removed earlier (unused). No other candidates found. | None |

## Fix 1: the agency dashboard no longer grows with scan history

**Problem.** `AgencyRepository.latest_completed_scans` selected (host, id) for every completed scan of the listed sites, newest first, and kept the first row per host in Python. The work and memory grow with history: an agency with 50 sites scanned daily and a 365-day window reads about 18,000 rows on every dashboard load, to use 50.

**Fix.** The database ranks scans per host (`row_number()` over host, newest first) and returns only rank 1. The result is identical (same host-to-scan map, ties still broken by id).

**Tests** (`test_agency_queries.py`): the newest completed scan wins; a newer failed scan is ignored; another workspace's scan of the same host name is ignored; unknown hosts are absent; and for twelve scans of one site the statement returns exactly one row. That last test fails on the old code (checked).

**Security impact:** none; the workspace filter is unchanged and a test covers a second workspace. **Migration:** none. **Rollback:** revert the commit.

## Fix 2: smaller first download

**Problem.** All pages were bundled into one file, so a visitor to the home or sign-in page also downloaded the dashboard, settings, analytics and report-viewing code. The build tool warned about the chunk size.

**Fix.** Signed-in pages other than Overview, and the long public pages (sample report, agency features, shared report), load when first opened.

| | Before | After |
|---|---|---|
| Main file | 498 kB (145 kB compressed) | 371 kB (114 kB compressed) |
| Largest page file | n/a | Integrations, 17 kB (5 kB compressed) |

About 22% less for the first visit. Opening a secondary page fetches a few kilobytes more (one request).

**Risk and how it is handled.** A tab left open across a release asks for a file name that no longer exists. Without handling, that would blank the app. `lazyPage` catches a failed load and shows "This page could not be loaded. Reload." (and the existing update notice already offers a reload). The Content-Security-Policy (`default-src 'self'`) allows the same-origin files. Tests: the page appears after loading; a failed load shows the message and a Reload button. All 230 frontend tests pass unchanged, lint, types, format and build are clean. The Playwright test runs in CI only.

**Rollback:** revert the commit.

## Left alone on purpose

- **Platform Health averages scan durations in application code** over the last 24 hours of scans (operator page only, polled every 30 s while open). At pilot volume this is a few rows; at thousands of scans a day it should become a database average. Not changed: speculative today.
- **Audit and session clean-up filter by time alone** while the audit index starts with the workspace. The hourly delete therefore scans the table. Harmless at this size; add an index on the timestamp only when the table is large enough to notice.
- **Scan history loads each scan's findings** to count them (a page of 25 reads up to about a thousand finding rows). A stored count per scan would avoid it. Not worth a migration yet.
- **Polling interval while a scan runs** (1.2 s) is fine for scans that last seconds to a minute; if scans get much longer, back off.
- **Load test:** run on 26 Oct, see `docs/load-test-results.md`. The 429 limits and the queue behaviour held; item 53 stays PARTIAL because the counters are per instance.

## Statuses for this phase

- Local development: READY.
- Owned or authorised sites: READY WITH CONDITIONS.
- Controlled external pilot (free plans): READY WITH CONDITIONS. No load-sensitive path is unbounded any more, but nothing has been measured under real traffic.
- Public commercial launch: NOT READY (load test, shared rate limits and the other earlier conditions).
