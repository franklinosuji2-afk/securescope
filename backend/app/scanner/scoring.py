"""Heuristic scoring. The score is a communication aid, not a measurement of security."""

from __future__ import annotations

from collections import Counter

from app.schemas.scan import SEVERITY_ORDER, Finding, Severity

PENALTY: dict[Severity, int] = {
    Severity.CRITICAL: 40,
    Severity.HIGH: 20,
    Severity.MEDIUM: 10,
    Severity.LOW: 4,
    Severity.INFO: 0,
}
GRADES: tuple[tuple[int, str], ...] = ((90, "A"), (80, "B"), (65, "C"), (50, "D"))


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counter = Counter(f.severity for f in findings)
    return {severity.value: counter.get(severity, 0) for severity in SEVERITY_ORDER}


def compute_score(findings: list[Finding]) -> tuple[int, str]:
    score = 100 - sum(PENALTY[f.severity] for f in findings)
    score = max(0, min(100, score))
    for threshold, grade in GRADES:
        if score >= threshold:
            return score, grade
    return score, "F"
