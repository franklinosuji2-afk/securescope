"""Compare two scans of one site by finding fingerprint.

A finding counts as the same finding when its fingerprint is the same, which is how the app already tracks a
finding from one scan to the next. Nothing here is estimated: a finding is new, resolved or unchanged only
because it is, or is not, in each scan's stored list.
"""

from __future__ import annotations

from app.schemas.compare import ComparedScan, ScanComparison
from app.schemas.scan import SEVERITY_ORDER, Finding, ScanDetail

NOTE = (
    "Findings are matched by their fingerprint. A finding that is missing from the newer scan was not "
    "detected there; that is not proof that it is fixed everywhere."
)


def _key(finding: Finding) -> str:
    return finding.fingerprint or f"{finding.id}:{finding.title}"


def _rank(finding: Finding) -> tuple[int, str]:
    return SEVERITY_ORDER.index(finding.severity), finding.title


def _summary(detail: ScanDetail) -> ComparedScan:
    return ComparedScan(
        id=detail.id,
        scanned_at=detail.created_at,
        status=detail.status,
        score=detail.score,
        grade=detail.grade,
    )


def compare_scans(first: ScanDetail, second: ScanDetail) -> ScanComparison:
    """The two scans in either order; the earlier one is treated as the baseline."""
    older, newer = sorted((first, second), key=lambda s: (s.created_at, s.id))
    before = {_key(f): f for f in older.findings}
    after = {_key(f): f for f in newer.findings}
    new = sorted((f for k, f in after.items() if k not in before), key=_rank)
    resolved = sorted((f for k, f in before.items() if k not in after), key=_rank)
    unchanged = sorted((f for k, f in after.items() if k in before), key=_rank)
    change = (
        newer.score - older.score if newer.score is not None and older.score is not None else None
    )
    return ScanComparison(
        host=newer.host,
        older=_summary(older),
        newer=_summary(newer),
        score_change=change,
        new_findings=new,
        resolved_findings=resolved,
        unchanged_findings=unchanged,
        note=NOTE,
    )
