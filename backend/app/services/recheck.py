"""Re-check one finding without running and storing a whole scan.

It makes the same requests as a scan (the page, one TLS look, the fixed-path probes and the DNS records) on the
same validated target, runs the same checks, and reports only on the one finding. It stores nothing, changes no
finding state and uses no scan allowance, so it never marks a finding resolved: only a full completed scan does
that, and the result says so. A check that did not run can never be reported as fixed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.config import Settings
from app.scanner.checks import assess
from app.scanner.fetcher import FetchError
from app.scanner.runner import collect
from app.schemas.scan import Finding, FindingRecheck

NEXT_STEP = "Run a full scan to update the score and mark it resolved."


async def recheck(host: str, url: str, finding: Finding, settings: Settings) -> FindingRecheck:
    now = datetime.now(UTC)

    def answer(outcome: str, message: str, evidence: str | None = None) -> FindingRecheck:
        return FindingRecheck(
            finding_id=finding.id,
            host=host,
            outcome=outcome,
            message=message,
            checked_at=now,
            evidence=evidence,
        )

    try:
        result, tls, probes, dns = await asyncio.wait_for(
            collect(url, settings), timeout=settings.max_scan_seconds
        )
    except FetchError as exc:
        return answer("could_not_check", f"The site could not be checked: {exc}")
    except TimeoutError:
        return answer("could_not_check", "The check took too long. Try again in a minute.")
    assessment = assess(result, tls, probes, dns)
    fresh = {f.id: f for f in assessment.findings}
    if finding.id in fresh:
        return answer(
            "still_present",
            "This finding is still there. If you just changed it, wait for caches to expire and try again.",
            fresh[finding.id].evidence,
        )
    prefixes = assessment.unverified_prefixes
    if prefixes and finding.id.startswith(prefixes):
        return answer(
            "could_not_check",
            "The check behind this finding could not run this time, so it is not possible to say whether "
            "it is fixed.",
        )
    return answer("not_seen", f"This check no longer reports it. {NEXT_STEP}")
