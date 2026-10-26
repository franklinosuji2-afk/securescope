"""The PDF cover: one page with the result at a glance, built only from the scan's own data."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.reporting.pdf import key_points, render_pdf
from app.schemas.scan import Severity
from app.tests.test_pdf_report import ID, NOW, detail, finding


def pages_of(findings, prepared_by=None, sample=False) -> list[str]:  # type: ignore[no-untyped-def]
    pdf = render_pdf(detail(findings), ID, NOW, prepared_by=prepared_by, sample=sample).content
    return [" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages]


def test_cover_is_one_page_with_the_result_at_a_glance() -> None:
    findings = [
        finding(1, title="Missing Content-Security-Policy header"),
        finding(2, title="Cookie without Secure flag"),
    ]
    findings[0] = findings[0].model_copy(update={"severity": Severity.HIGH})
    pages = pages_of(findings, prepared_by="Example Agency")
    first = pages[0]
    for expected in (
        "a.example",
        "80",
        "Grade B",
        "Overall risk rating",
        "High",
        "Summary",
        ID,
        "Example Agency",
        "Start with",
    ):
        assert expected.lower() in first.lower(), expected
    assert "2 findings to review, 1 of high or critical severity." in first
    assert "Missing Content-Security-Policy header" in first
    assert "not a penetration test" in first


def test_findings_start_on_page_two_and_never_on_the_cover() -> None:
    pages = pages_of([finding(1), finding(2)])
    assert "What this means" not in pages[0] and "How to fix it" not in pages[0]
    assert pages[1].startswith("Findings") and "What this means" in pages[1]


def test_cover_stays_on_one_page_with_many_long_findings_and_long_names() -> None:
    long = "Very long title " * 12
    findings = [finding(n, title=f"{n} {long}") for n in range(1, 40)]
    pages = pages_of(findings, prepared_by="A" * 120, sample=True)
    assert "Summary" in pages[0] and "and 36 more" in pages[0]
    assert "Findings" not in pages[0].split("Summary")[0]
    assert pages[1].startswith("Findings")
    assert "SAMPLE REPORT" in pages[0]


def test_cover_for_a_clean_scan_says_it_is_not_proof() -> None:
    first = pages_of([])[0]
    assert "The checks did not find any problems." in first
    assert "Start with" not in first
    assert "not proof" in first and "not a penetration test" in first


def test_key_points_use_only_the_findings_given() -> None:
    items = [{"title": "A"}, {"title": "A"}, {"title": "B"}, {"title": "C"}, {"title": "D"}]
    result = key_points(items, {"critical": 1, "high": 1})
    assert result["top"] == ["A", "B", "C"] and result["more"] == 1
    assert result["headline"] == "5 findings to review, 2 of high or critical severity."
    assert key_points([], {})["headline"] == "The checks did not find any problems."
    assert key_points([{"title": "A"}], {})["headline"] == "1 finding to review."


def test_hostile_text_stays_inert_on_the_cover() -> None:
    f = finding(1, title="<script>alert(1)</script>")
    first = pages_of([f], prepared_by="<img src=x onerror=alert(1)>")[0]
    assert "<script>alert(1)</script>" in first  # shown as text, not run
