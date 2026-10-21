"""PDF reports: built from the HTML template, hostile text stays inert, long reports paginate."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.reporting.pdf import render_html, render_pdf
from app.schemas.scan import Finding, ScanDetail, ScanStatus, Severity, TargetMetadata

NOW = datetime(2026, 10, 18, 20, 11, tzinfo=UTC)


def detail(findings: list[Finding], status: ScanStatus = ScanStatus.COMPLETED, error: str | None = None) -> ScanDetail:
    completed = status is ScanStatus.COMPLETED
    return ScanDetail(
        id="a" * 32,
        target_url="https://a.example/",
        host="a.example",
        status=status,
        score=80 if completed else None,
        grade="B" if completed else None,
        created_at=NOW,
        finished_at=NOW,
        counts={"medium": len(findings)} if completed else {},
        error=error,
        metadata=TargetMetadata(requested_url="https://a.example/", host="a.example", checks_run=["https"])
        if completed
        else None,
        findings=findings if completed else [],
        score_note="n",
    )


def finding(n: int = 1, evidence: str | None = "Header not present.", title: str | None = None) -> Finding:
    return Finding(
        id=f"SS-TEST-{n:03d}",
        title=title or f"Finding number {n}",
        severity=Severity.MEDIUM,
        category="Security headers",
        description="A description of the problem.",
        evidence=evidence,
        remediation="Do the fix.",
    )


def text_of(pdf: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(pdf))
    return "\n".join(page.extract_text() for page in reader.pages), len(reader.pages)


ID = "SSR-TESTREPORT"


def to_pdf(d: ScanDetail) -> bytes:
    return render_pdf(d, ID, NOW).content


def test_report_contains_everything_a_client_needs() -> None:
    pdf = to_pdf(detail([finding(1, title="Content-Security-Policy header is missing")]))
    assert pdf.startswith(b"%PDF-")
    text, pages = text_of(pdf)
    assert pages >= 2
    for expected in (
        "SecureScope",  # branding
        "Website security report",
        ID,  # report ID
        "18 October 2026",  # scan date
        "a.example",
        "https://a.example/",
        "Overall risk rating",
        "Medium",  # the rating, from the findings
        "Content-Security-Policy header is missing",
        "SS-TEST-001",
        "Affected URL: https://a.example/",
        "Header not present.",  # evidence
        "How to fix it.",
        "Do the fix.",  # remediation
        "Remediation plan",
        "not a penetration test",
        "Limits of this report",
    ):
        # Headings are upper-cased by the stylesheet, so compare without regard to case.
        assert expected.lower() in text.lower(), expected


def test_the_overall_risk_follows_the_worst_finding_that_still_counts() -> None:
    from app.reporting.risk import overall_risk
    from app.schemas.scan import FindingStatus

    def with_severity(severity: Severity, status: FindingStatus = FindingStatus.OPEN) -> Finding:
        return finding(1).model_copy(update={"severity": severity, "status": status})

    assert overall_risk(detail([])).level == "minimal"
    assert overall_risk(detail([with_severity(Severity.LOW)])).level == "low"
    assert overall_risk(detail([with_severity(Severity.MEDIUM), with_severity(Severity.LOW)])).level == "medium"
    assert overall_risk(detail([with_severity(Severity.CRITICAL)])).level == "critical"
    # A finding the team marked as a false positive no longer counts.
    dismissed = with_severity(Severity.CRITICAL, FindingStatus.FALSE_POSITIVE)
    assert overall_risk(detail([dismissed])).level == "minimal"


def test_severity_summary_counts_each_level() -> None:
    from app.reporting.risk import severity_counts

    findings = [finding(1), finding(2), finding(3).model_copy(update={"severity": Severity.HIGH})]
    assert severity_counts(detail(findings)) == {"critical": 0, "high": 1, "medium": 2, "low": 0, "info": 0}


def test_a_clean_scan_says_so_and_does_not_claim_security() -> None:
    text, _ = text_of(to_pdf(detail([])))
    assert "did not find any problems" in text
    assert "not proof of security" in text
    assert "Minimal" in text


def test_exposed_file_findings_name_the_exact_address() -> None:
    env = finding(1).model_copy(update={"id": "SS-EXPOSE-ENV-001", "title": "Settings file exposed"})
    text, _ = text_of(to_pdf(detail([env])))
    assert "https://a.example/.env" in text


def test_hostile_evidence_is_printed_as_text_and_cannot_change_the_document() -> None:
    nasty = (
        "<b>bold</b> <img src='http://169.254.169.254/latest'/> <link rel=stylesheet href='file:///etc/passwd'> "
        '<a href="https://evil.example">click</a> <style>body{display:none}</style> & &amp; '
        "\x00\x1b[31m 日本語 " + "W" * 500
    )
    findings = [finding(1, evidence=nasty, title="<script>alert(1)</script>")]
    html = render_html(detail(findings), ID, NOW)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<img src='http://169.254" not in html and "<a href=\"https://evil" not in html
    pdf = to_pdf(detail(findings))
    text, _ = text_of(pdf)
    for literal in ("<b>bold</b>", "<script>alert(1)</script>", "& &amp;"):
        assert literal in text, literal
    assert "\x00" not in text and "\x1b" not in text
    # The report has no links, scripts or embedded files, and nothing was fetched while building it.
    for forbidden in (b"/URI", b"/Launch", b"/JavaScript", b"/JS", b"/OpenAction", b"/EmbeddedFile"):
        assert forbidden not in pdf, forbidden


def test_the_renderer_refuses_to_load_anything_from_the_network_or_disk() -> None:
    from app.reporting.pdf import _refuse_fetch

    with pytest.raises(ValueError):
        _refuse_fetch("http://169.254.169.254/latest")
    with pytest.raises(ValueError):
        _refuse_fetch("file:///etc/passwd")


def test_a_very_long_report_paginates_and_every_page_has_a_footer() -> None:
    blob = "word " * 120
    findings = [finding(i, evidence=blob) for i in range(1, 31)]
    text, pages = text_of(to_pdf(detail(findings)))
    assert pages > 4
    assert f"Page {pages} of {pages}" in text
    assert f"{ID}" in text and "SS-TEST-030" in text
