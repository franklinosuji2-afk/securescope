"""PDF export: valid output, hostile text stays inert, long reports paginate."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.reporting.reports import to_pdf
from app.schemas.scan import Finding, ScanDetail, ScanStatus, Severity, TargetMetadata
from app.tests.test_finding_lifecycle import API, member_client, run_scan

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


def test_report_contains_the_same_facts_as_the_other_formats() -> None:
    pdf = to_pdf(detail([finding(1, title="Content-Security-Policy header is missing")]))
    assert pdf.startswith(b"%PDF-")
    text, pages = text_of(pdf)
    assert pages == 1
    for expected in (
        "SecureScope report",
        "a.example",
        "https://a.example/",
        "80/100 (grade B)",
        "Content-Security-Policy header is missing",
        "[MEDIUM]",
        "SS-TEST-001",
        "Header not present.",
        "Do the fix.",
        "not a penetration test",
        "Limits of this scan",
        "Page 1",
    ):
        assert expected in text, expected


def test_a_clean_scan_says_so_and_does_not_claim_security() -> None:
    text, _ = text_of(to_pdf(detail([])))
    assert "No findings from the implemented checks." in text
    assert "not proof of security" in text


def test_failed_and_cancelled_scans_still_produce_a_valid_report() -> None:
    for status, error in ((ScanStatus.FAILED, "Connection refused."), (ScanStatus.CANCELLED, "Cancelled.")):
        text, _ = text_of(to_pdf(detail([], status, error)))
        assert status.value in text and error in text
        assert "Findings" not in text.replace("Findings by severity", "")  # no findings section


def test_hostile_evidence_is_printed_as_text_and_cannot_change_the_document() -> None:
    nasty = (
        "<b>bold</b> <para backColor=red>x</para> <img src='file:///etc/passwd'/> "
        '<a href="https://evil.example">click</a> <font color="red">r</font> & &amp; '
        "\x00\x1b[31m‮日本語 \U0001f600 " + "W" * 500
    )
    pdf = to_pdf(detail([finding(1, evidence=nasty, title="<script>alert(1)</script>")]))
    text, _ = text_of(pdf)
    # Markup shows up literally instead of being interpreted.
    for literal in ("<b>bold</b>", "<img src='file:///etc/passwd'/>", "<script>alert(1)</script>", "& &amp;"):
        assert literal in text, literal
    assert "\x00" not in text and "\x1b" not in text
    # No links, launch actions or scripts can be embedded by a remote server's header value.
    for forbidden in (b"/URI", b"/Launch", b"/JavaScript", b"/JS", b"/OpenAction", b"/EmbeddedFile"):
        assert forbidden not in pdf, forbidden
    assert len(PdfReader(BytesIO(pdf)).pages[0].get("/Annots", [])) == 0


def test_a_very_long_report_paginates_and_every_page_has_a_footer() -> None:
    text_blob = "word " * 200
    findings = [finding(i, evidence=text_blob) for i in range(1, 41)]
    text, pages = text_of(to_pdf(detail(findings)))
    assert pages > 3
    assert f"Page {pages}" in text
    assert "SS-TEST-040" in text


def test_pdf_export_endpoint(local_client: TestClient, mock_server: str) -> None:
    scan = run_scan(local_client, mock_server)
    response = local_client.get(f"{API}/scans/{scan['id']}/report?format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;") and disposition.endswith('.pdf"')
    assert response.content.startswith(b"%PDF-")
    text, _ = text_of(response.content)
    assert "127.0.0.1" in text and "Content-Security-Policy header is missing" in text
    audit = local_client.get(f"{API}/audit-events?event_type=report.exported").json()
    assert audit["total"] == 1


def test_viewers_may_export_pdf_and_unknown_formats_are_rejected(
    local_client: TestClient, mock_server: str
) -> None:
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    scan = run_scan(local_client, mock_server)
    viewer = member_client(local_client, org, "viewer@example.com", "VIEWER")
    assert viewer.get(f"{API}/scans/{scan['id']}/report?format=pdf").status_code == 200
    assert local_client.get(f"{API}/scans/{scan['id']}/report?format=docx").status_code == 422


@pytest.mark.parametrize("status", [ScanStatus.QUEUED, ScanStatus.RUNNING])
def test_unfinished_scans_have_no_report(status: ScanStatus, local_client: TestClient) -> None:
    state = local_client.app.state.s  # type: ignore[attr-defined]
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    user = local_client.get(f"{API}/auth/me").json()["id"]
    scan_id = state.repo.create_scan(org, user, "https://a.example/", "a.example")
    if status is ScanStatus.RUNNING:
        state.repo.mark_running(scan_id)
    assert local_client.get(f"{API}/scans/{scan_id}/report?format=pdf").status_code == 409
