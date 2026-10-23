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


def method_lines() -> list[str]:
    """What the score is, written from the same numbers the code uses so the text cannot drift from it."""
    penalties = ", ".join(f"{s.value} {PENALTY[s]}" for s in SEVERITY_ORDER if PENALTY[s] > 0)
    grades = ", ".join(f"{g} from {t}" for t, g in GRADES) + ", F below " + str(GRADES[-1][0])
    return [
        f"The score starts at 100. Each finding takes off points by severity ({penalties}); informational "
        "notes take off none. The result is kept between 0 and 100.",
        f"Grades: {grades}.",
        "The same findings always give the same score. The score only reflects the passive checks that ran in "
        "this scan, so it measures how many of those checks reported a problem and how serious each was.",
        "It does not measure how secure the website is overall. It is not a penetration test, and it says "
        "nothing about code, logins, business logic, servers or anything the checks did not look at.",
    ]


def score_note(findings: list[Finding], score: int) -> str:
    """One sentence that ties this scan's score to its findings, including the 100-with-notes case."""
    scored = [f for f in findings if PENALTY[f.severity] > 0]
    notes = len(findings) - len(scored)
    if not scored and notes:
        return (
            f"{score}/100 means none of the checks that were run reported a scored finding. The {notes} "
            "informational note(s) below do not change the score. This is not proof that the site is secure."
        )
    if not scored:
        return (
            f"{score}/100 means none of the checks that were run reported a problem. "
            "This is not proof that the site is secure."
        )
    taken = 100 - score if score > 0 else 100
    return (
        f"{score}/100: {len(scored)} scored finding(s) account for {taken} point(s) of the deduction"
        + (f", and {notes} informational note(s) take off none" if notes else "")
        + ". The score is a rough guide, not a measurement of security."
    )
