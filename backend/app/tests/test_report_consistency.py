"""The same scan, exported in every format, must say the same things.

Each format is rendered from one scan and checked for the facts a reader relies on: every finding, the score,
what could not be checked, and the statement that this is not proof of security or a penetration test.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.reporting import reports
from app.reporting.csv_export import to_csv
from app.reporting.pdf import render_pdf
from app.schemas.scan import (
    Finding,
    FindingStatus,
    ScanDetail,
    ScanStatus,
    Severity,
    SkippedCheck,
    TargetMetadata,
)

NOW = datetime(2026, 10, 18, 20, 11, tzinfo=UTC)

FINDINGS = [
    ("SS-HDR-CSP-001", "Missing Content Security Policy", Severity.MEDIUM, FindingStatus.OPEN),
    ("SS-COOKIE-001", "Cookie without the Secure flag", Severity.LOW, FindingStatus.ACCEPTED_RISK),
    ("SS-DISC-SRV-001", "Server header shows a version", Severity.INFO, FindingStatus.FALSE_POSITIVE),
    ("SS-HDR-REF-001", "No Referrer-Policy", Severity.LOW, FindingStatus.RESOLVED),
]


def make_detail() -> ScanDetail:
    findings = [
        Finding(
            id=fid,
            title=title,
            severity=sev,
            category="Security headers",
            description="A description.",
            remediation="Do the fix.",
            fingerprint=f"fp-{fid}",
            status=status,
        )
        for fid, title, sev, status in FINDINGS
    ]
    return ScanDetail(
        id="a" * 32,
        target_url="https://a.example/",
        host="a.example",
        status=ScanStatus.COMPLETED,
        score=87,
        grade="B",
        created_at=NOW,
        finished_at=NOW,
        counts={"medium": 1, "low": 2, "info": 1},
        metadata=TargetMetadata(
            requested_url="https://a.example/",
            host="a.example",
            checks_run=["https", "csp"],
            checks_skipped=[SkippedCheck(name="spf", reason="DNS did not answer in time")],
        ),
        findings=findings,
    )


def pdf_text(detail: ScanDetail) -> str:
    reader = PdfReader(BytesIO(render_pdf(detail, "SSR-TEST", NOW).content))
    return " ".join(" ".join(p.extract_text().split()) for p in reader.pages)


def render(fmt: str, detail: ScanDetail) -> str:
    if fmt == "md":
        return reports.to_markdown(detail)
    if fmt == "html":
        return reports.to_html(detail)
    if fmt == "json":
        return reports.to_json(detail)
    if fmt == "csv":
        return to_csv(detail)
    return pdf_text(detail)


@pytest.mark.parametrize("fmt", ["md", "html", "json", "csv", "pdf"])
def test_every_format_lists_every_finding_whatever_its_status(fmt: str) -> None:
    text = render(fmt, make_detail())
    for fid, title, _sev, status in FINDINGS:
        if fmt == "pdf" and status is FindingStatus.FALSE_POSITIVE:
            continue  # left out of the client PDF on purpose; the next test checks that it says so
        assert fid in text or title in text, f"{fmt} is missing {fid}"


def test_the_pdf_says_how_many_false_positives_it_leaves_out() -> None:
    text = pdf_text(make_detail())
    assert "1 finding marked as a false positive by the team is not listed" in text
    detail = make_detail()
    for f in detail.findings:
        f.status = FindingStatus.OPEN
    assert "false positive" not in pdf_text(detail).lower()


def test_the_other_formats_label_a_false_positive_instead_of_dropping_it() -> None:
    for fmt in ("md", "html"):
        text = render(fmt, make_detail())
        assert "Server header shows a version" in text
        assert "false positive" in text.lower()


@pytest.mark.parametrize("fmt", ["md", "html", "json", "pdf"])
def test_every_format_carries_the_score(fmt: str) -> None:
    text = render(fmt, make_detail())
    assert "87" in text


@pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
def test_every_readable_format_says_what_could_not_be_checked(fmt: str) -> None:
    text = render(fmt, make_detail())
    assert "DNS did not answer in time" in text, f"{fmt} hides a check that did not run"


@pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
def test_every_readable_format_says_it_is_not_proof_or_a_pen_test(fmt: str) -> None:
    text = render(fmt, make_detail()).lower()
    assert "not a penetration test" in text, fmt
    assert "not proof" in text, fmt


@pytest.mark.parametrize("fmt", ["md", "html", "pdf"])
def test_a_resolved_finding_is_never_described_as_fixed(fmt: str) -> None:
    text = render(fmt, make_detail()).lower()
    assert "no longer detected" in text
    assert "does not prove a fix" in text or "not prove a fix" in text or "not proof" in text


def test_csv_rows_match_the_findings_and_json_matches_the_model() -> None:
    detail = make_detail()
    rows = list(csv.DictReader(io.StringIO(to_csv(detail))))
    assert len(rows) == len(FINDINGS)
    data = json.loads(reports.to_json(detail))
    assert [f["id"] for f in data["findings"]] == [f[0] for f in FINDINGS]
    assert data["score"] == 87
