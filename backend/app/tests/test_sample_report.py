"""The public sample report must be what the scanner really produces for the site it describes.

The page's findings, scores and check lists live in ``frontend/src/sample/sampleReport.json``. This test runs
the real checks against the same described site and compares, so the sample cannot drift from the product.
Set ``UPDATE_SAMPLE_REPORT=1`` to rewrite the file after an intentional change to a check.
"""

from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.scanner.checks import CHECK_LABELS, assess
from app.scanner.fetcher import FetchResult, ProbeResponse
from app.scanner.scoring import GRADES, PENALTY, compute_score
from app.scanner.tls import TlsObservation
from app.tests.test_scan_accuracy import GOOD_HEADERS, clean_probes, good_tls, page, probe

FIXTURE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "sample" / "sampleReport.json"


def sample_inputs() -> tuple[FetchResult, TlsObservation, dict[str, ProbeResponse]]:
    """The described example site: what the page, TLS and probes of example.com look like."""
    headers = [
        h for h in GOOD_HEADERS if h[0] not in ("content-security-policy", "strict-transport-security")
    ]
    headers += [
        ("strict-transport-security", "max-age=300"),
        ("set-cookie", "session=REDACTED; Path=/; Secure; SameSite=Lax"),
    ]
    probes = clean_probes(**{"/.well-known/security.txt": probe("/.well-known/security.txt", 404)})
    return page(headers), good_tls(), probes


def build() -> dict[str, object]:
    assessment = assess(*sample_inputs())
    score, grade = compute_score(assessment.findings)
    found = {p for f in assessment.findings for p in [f.id]}
    passed = [
        CHECK_LABELS[name][0]
        for name in assessment.checks_run
        if name in CHECK_LABELS
        and not any(fid.startswith(prefix) for fid in found for prefix in CHECK_LABELS[name][1])
    ]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings = sorted(assessment.findings, key=lambda f: (order[f.severity.value], f.id))
    return {
        "domain": "example.com",
        "score": score,
        "grade": grade,
        "penalties": {sev.value: pts for sev, pts in PENALTY.items()},
        "grade_bands": [{"min": lo, "grade": g} for lo, g in GRADES],
        "checks_run": len(assessment.checks_run),
        "checks_passed": passed,
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity.value,
                "category": f.category,
                "description": f.description,
                "evidence": f.evidence,
                "remediation": f.remediation,
            }
            for f in findings
        ],
    }


def test_sample_report_matches_what_the_scanner_produces() -> None:
    built = build()
    if os.environ.get("UPDATE_SAMPLE_REPORT") == "1":
        FIXTURE.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == built


def test_sample_report_uses_only_the_reserved_example_domain() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["domain"] == "example.com"
    blob = json.dumps(data["findings"])
    assert "example.com" in blob
    assert "http://" not in blob.replace("http://example.com", "")


# --- the PDF offered on the home page --------------------------------------------------------------

PDF = Path(__file__).resolve().parents[3] / "frontend" / "public" / "sample-report.pdf"


def pdf_text() -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(PDF.read_bytes())).pages)


def test_the_sample_pdf_says_it_is_a_sample_and_matches_the_sample_data() -> None:
    assert PDF.read_bytes().startswith(b"%PDF-")
    assert PDF.stat().st_size < 200_000  # small enough to open at once
    text = " ".join(pdf_text().split())
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "SAMPLE REPORT" in text and "Not a real customer or scan" in text
    assert "SecureScope" in text and "SSR-SAMPLE0000" in text
    assert f"Security score {data['score']}/100 (grade {data['grade']})" in text
    for finding in data["findings"]:
        assert finding["title"] in text, f"regenerate the PDF: {finding['title']!r} is missing"
    assert "http://" not in text.replace("http://example.com", "")


def test_only_the_sample_report_carries_the_sample_label() -> None:
    from datetime import UTC, datetime

    from app.reporting.pdf import render_html
    from app.tests.test_pdf_report import detail, finding

    real = render_html(detail([finding(1)]), "SSR-REAL00000000", datetime(2026, 10, 18, tzinfo=UTC))
    assert "SAMPLE REPORT" not in real
    flagged = render_html(
        detail([finding(1)]), "SSR-SAMPLE0000", datetime(2026, 10, 18, tzinfo=UTC), sample=True
    )
    assert "SAMPLE REPORT" in flagged
