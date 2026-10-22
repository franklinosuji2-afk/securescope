"""The public sample report must be what the scanner really produces for the site it describes.

The page's findings, scores and check lists live in ``frontend/src/sample/sampleReport.json``. This test runs
the real checks against the same described site and compares, so the sample cannot drift from the product.
Set ``UPDATE_SAMPLE_REPORT=1`` to rewrite the file after an intentional change to a check.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.scanner.checks import CHECK_LABELS, assess
from app.scanner.scoring import GRADES, PENALTY, compute_score
from app.tests.test_scan_accuracy import GOOD_HEADERS, clean_probes, good_tls, page, probe

FIXTURE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "sample" / "sampleReport.json"


def build() -> dict[str, object]:
    headers = [
        h for h in GOOD_HEADERS if h[0] not in ("content-security-policy", "strict-transport-security")
    ]
    headers += [
        ("strict-transport-security", "max-age=300"),
        ("set-cookie", "session=REDACTED; Path=/; Secure; SameSite=Lax"),
    ]
    probes = clean_probes(**{"/.well-known/security.txt": probe("/.well-known/security.txt", 404)})
    assessment = assess(page(headers), good_tls(), probes)
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
