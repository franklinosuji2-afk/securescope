"""Builds frontend/public/sample-report.pdf, the example report offered on the home page.

The findings come from SecureScope's own checks run against a described test site (example.com, a domain
reserved for documentation), exactly as the sample report page does. Nothing is scanned over the network and
no customer data is involved. Run it after an intentional change to a check or to the report layout:

    cd backend && python ../scripts/make_sample_pdf.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.reporting.pdf import render_pdf  # noqa: E402
from app.scanner.checks import CHECK_LABELS, assess  # noqa: E402
from app.scanner.scoring import compute_score  # noqa: E402
from app.schemas.scan import ScanDetail, ScanStatus, TargetMetadata  # noqa: E402
from app.tests.test_sample_report import sample_inputs  # noqa: E402

OUT = ROOT / "frontend" / "public" / "sample-report.pdf"
WHEN = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
REPORT_ID = "SSR-SAMPLE0000"


def build_detail() -> ScanDetail:
    page, tls, probes = sample_inputs()
    assessment = assess(page, tls, probes)
    score, grade = compute_score(assessment.findings)
    counts: dict[str, int] = {}
    for finding in assessment.findings:
        counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
    return ScanDetail(
        id="0" * 32,
        target_url="https://example.com/",
        host="example.com",
        status=ScanStatus.COMPLETED,
        score=score,
        grade=grade,
        created_at=WHEN,
        finished_at=WHEN,
        counts=counts,
        metadata=TargetMetadata(
            requested_url="https://example.com/",
            host="example.com",
            checks_run=[name for name in assessment.checks_run if name in CHECK_LABELS],
        ),
        findings=assessment.findings,
    )


def main() -> None:
    report = render_pdf(build_detail(), REPORT_ID, WHEN, prepared_by="Example Agency (sample)", sample=True)
    OUT.write_bytes(report.content)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(report.content)} bytes)")


if __name__ == "__main__":
    main()
