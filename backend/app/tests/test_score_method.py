"""The written score method matches the code, and reports say what the score does and does not mean."""

from __future__ import annotations

import re
from pathlib import Path

from app.reporting.guidance import all_guidance
from app.reporting.pdf import render_html
from app.reporting.reports import to_html, to_markdown
from app.scanner.scoring import GRADES, PENALTY, compute_score, method_lines, score_note
from app.schemas.scan import Finding, Severity
from app.tests.test_pdf_report import NOW, detail, finding

DOC = (Path(__file__).resolve().parents[3] / "docs" / "SCORING_AND_SEVERITY.md").read_text(encoding="utf-8")


def make(severity: Severity, n: int = 1) -> list[Finding]:
    return [
        Finding(id=f"SS-T-{i}", title="t", severity=severity, category="c", description="d", remediation="r")
        for i in range(n)
    ]


def test_method_text_uses_the_real_numbers() -> None:
    text = " ".join(method_lines())
    for severity, points in PENALTY.items():
        if points:
            assert f"{severity.value} {points}" in text
    for threshold, grade in GRADES:
        assert f"{grade} from {threshold}" in text
    assert "not a penetration test" in text


def test_the_document_lists_the_same_penalties_and_grades() -> None:
    for severity, points in PENALTY.items():
        assert re.search(rf"\|\s*{severity.value}\s*\|\s*{points}\s*\|", DOC, re.I), severity
    for threshold, grade in GRADES:
        assert re.search(rf"\|\s*{grade}\s*\|\s*{threshold}", DOC), grade


def test_every_guided_rule_is_in_the_severity_table() -> None:
    missing = [rule for rule in all_guidance() if rule not in DOC]
    assert missing == []


def test_scoring_is_deterministic_and_order_independent() -> None:
    a = make(Severity.HIGH) + make(Severity.LOW, 2) + make(Severity.INFO, 3)
    assert compute_score(a) == compute_score(list(reversed(a))) == (72, "C")


def test_a_perfect_score_with_notes_is_explained_and_not_called_secure() -> None:
    note = score_note(make(Severity.INFO, 3), 100)
    assert "3 informational" in note and "do not change the score" in note
    assert "not proof" in note
    assert "not proof" in score_note([], 100)


def test_a_deduction_is_tied_to_the_findings() -> None:
    note = score_note(make(Severity.MEDIUM, 2) + make(Severity.INFO), 80)
    assert "2 scored" in note and "20 point" in note and "1 informational" in note


def test_every_report_format_carries_the_method() -> None:
    d = detail([finding(1)])
    for out in (render_html(d, "SSR-TEST", NOW), to_html(d), to_markdown(d)):
        assert "How the score is worked out" in out
        assert "does not measure how secure" in out


def test_certificate_failures_are_graded_by_how_sure_the_scanner_is() -> None:
    from app.scanner.checks import check_tls_certificate
    from app.scanner.tls import TlsObservation
    from app.tests.test_scan_accuracy import GOOD_HEADERS, page

    got = {}
    for kind in ("expired", "not_yet_valid", "hostname_mismatch", "untrusted", "other"):
        tls = TlsObservation(outcome="verification_failed", failure_kind=kind, detail="x")
        f = check_tls_certificate(page(GOOD_HEADERS), tls)[0]
        got[kind] = (f.severity.value, f.confidence.value)
    assert got == {
        "expired": ("high", "high"),
        "hostname_mismatch": ("high", "high"),
        "untrusted": ("high", "high"),
        "not_yet_valid": ("medium", "medium"),
        "other": ("medium", "medium"),
    }


def test_dns_findings_name_the_records_not_a_page() -> None:
    dns = Finding(
        id="SS-DNS-CAA-001", title="t", severity=Severity.INFO, category="c", description="d", remediation="r"
    )
    html = render_html(detail([dns, finding(1)]), "SSR-TEST", NOW)
    assert "Affected records: DNS records of a.example" in html
    assert "Affected URL: https://a.example/" in html
