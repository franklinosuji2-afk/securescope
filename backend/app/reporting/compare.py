"""Compare two scans of one site by finding fingerprint.

A finding counts as the same finding when its fingerprint is the same, which is how the app already tracks a
finding from one scan to the next. Nothing here is estimated: a finding is new, resolved or unchanged only
because it is, or is not, in each scan's stored list.
"""

from __future__ import annotations

from app.scanner.checks import CHECK_LABELS
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


def _skipped_prefixes(detail: ScanDetail) -> tuple[tuple[str, ...], list[str]]:
    """Finding-id prefixes and labels of the checks that could not be evaluated in this scan."""
    skipped = detail.metadata.checks_skipped if detail.metadata else []
    prefixes: list[str] = []
    labels: list[str] = []
    for item in skipped:
        label, owned = CHECK_LABELS.get(item.name, (item.name, ()))
        prefixes.extend(owned)
        labels.append(label)
    return tuple(prefixes), labels


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
    # A check that did not run says nothing about its findings, so they are neither resolved nor new.
    older_skipped, older_labels = _skipped_prefixes(older)
    newer_skipped, newer_labels = _skipped_prefixes(newer)

    def unknown(finding: Finding, skipped: tuple[str, ...]) -> bool:
        return bool(skipped) and finding.id.startswith(skipped)

    new_all = [f for k, f in after.items() if k not in before]
    resolved_all = [f for k, f in before.items() if k not in after]
    new = sorted((f for f in new_all if not unknown(f, older_skipped)), key=_rank)
    resolved = sorted((f for f in resolved_all if not unknown(f, newer_skipped)), key=_rank)
    not_comparable = sorted(
        [f for f in new_all if unknown(f, older_skipped)]
        + [f for f in resolved_all if unknown(f, newer_skipped)],
        key=_rank,
    )
    unchanged = sorted((f for k, f in after.items() if k in before), key=_rank)
    change = newer.score - older.score if newer.score is not None and older.score is not None else None
    return ScanComparison(
        host=newer.host,
        older=_summary(older),
        newer=_summary(newer),
        score_change=change,
        new_findings=new,
        resolved_findings=resolved,
        unchanged_findings=unchanged,
        not_comparable_findings=not_comparable,
        not_comparable_checks=sorted({*older_labels, *newer_labels}),
        note=NOTE,
    )
