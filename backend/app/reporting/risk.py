"""The overall risk rating shown to clients, in plain words.

It is derived from the findings that still count (a finding marked as a false positive does not), so the
rating, the severity summary and the findings list in a report always agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.scan import SEVERITY_ORDER, Finding, FindingStatus, ScanDetail, Severity


@dataclass(frozen=True)
class RiskRating:
    level: str  # critical | high | medium | low | minimal
    label: str
    summary: str


_SUMMARIES = {
    "critical": "Serious problems were found that should be fixed right away.",
    "high": "Important problems were found. Plan to fix them soon.",
    "medium": "Some weaknesses were found. They are worth fixing, but they are not an emergency.",
    "low": "Only minor issues were found. Fix them when convenient.",
    "minimal": "None of the checks found a problem. This is a good sign, but it does not prove the site is secure.",
}


def counting_findings(detail: ScanDetail) -> list[Finding]:
    return [f for f in detail.findings if f.status is not FindingStatus.FALSE_POSITIVE]


def severity_counts(detail: ScanDetail) -> dict[str, int]:
    findings = counting_findings(detail)
    return {s.value: sum(1 for f in findings if f.severity is s) for s in SEVERITY_ORDER}


def overall_risk(detail: ScanDetail) -> RiskRating:
    counts = severity_counts(detail)
    if counts[Severity.CRITICAL.value]:
        level = "critical"
    elif counts[Severity.HIGH.value]:
        level = "high"
    elif counts[Severity.MEDIUM.value]:
        level = "medium"
    elif counts[Severity.LOW.value]:
        level = "low"
    else:
        level = "minimal"
    labels = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "minimal": "Minimal"}
    return RiskRating(level, labels[level], _SUMMARIES[level])
