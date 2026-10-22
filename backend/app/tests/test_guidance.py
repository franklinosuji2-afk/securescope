"""Remediation guidance: complete, safe, in step with the web app, and present in the PDF."""

from __future__ import annotations

import re
from pathlib import Path

from app.reporting.guidance import all_guidance, guidance_for
from app.reporting.pdf import build_context, render_html
from app.scanner.checks import assess
from app.schemas.scan import Finding
from app.tests.test_scan_accuracy import GOOD_HEADERS, clean_probes, good_tls, page

ROOT = Path(__file__).resolve().parents[3]
CHECKS_SOURCE = " ".join(
    (ROOT / "backend" / "app" / "scanner" / name).read_text(encoding="utf-8")
    for name in ("checks.py", "page_checks.py", "dns_checks.py")
)
FRONTEND_COPY = ROOT / "frontend" / "src" / "guidance.json"


def emitted_ids() -> set[str]:
    """Every full finding id the scanner source can produce (prefixes used for matching end in a dash)."""
    return {m for m in re.findall(r'"(SS-[A-Z0-9-]*-\d{3})"', CHECKS_SOURCE)}


def test_every_finding_the_scanner_can_report_has_guidance() -> None:
    missing = sorted(emitted_ids() - set(all_guidance()))
    assert not missing, f"no guidance for {missing}"


def test_guidance_has_no_unknown_ids() -> None:
    assert set(all_guidance()) <= emitted_ids()


def test_references_are_https_and_examples_are_nonempty() -> None:
    for key, guide in all_guidance().items():
        assert all(r.url.startswith("https://") for r in guide.references), key
        assert all(x.code.strip() and x.label.strip() for x in guide.fixes), key
        assert all(step.strip() for step in guide.verify), key


def test_guidance_names_no_real_domains_or_secrets() -> None:
    blob = " ".join(g.model_dump_json() for g in all_guidance().values())
    assert not re.search(r"(?i)(password|secret|token)\s*[:=]\s*\S{6,}", blob)


def test_web_app_copy_matches_the_source_of_truth() -> None:
    source = (Path(__file__).resolve().parents[1] / "reporting" / "guidance.json").read_text(encoding="utf-8")
    assert FRONTEND_COPY.read_text(encoding="utf-8") == source


def test_header_findings_offer_the_common_server_examples() -> None:
    labels = " ".join(x.label for x in all_guidance()["SS-HDR-CSP-001"].fixes)
    assert "Nginx" in labels and "Apache" in labels and "Cloudflare" in labels
    assert guidance_for("SS-NOT-A-REAL-ID") is None


def test_the_pdf_carries_guidance_and_escapes_it() -> None:
    from app.schemas.scan import Severity
    from app.tests.test_pdf_report import detail

    real = Finding(
        id="SS-HDR-CSP-001",
        title="Content-Security-Policy header is missing",
        severity=Severity.MEDIUM,
        category="Security headers",
        description="d",
        evidence="e",
        remediation="r",
    )
    scan = detail([real])
    html = render_html(scan, "REPORT-1")
    assert "How to verify the fix" in html
    assert "Nginx" in html
    assert "&lt;your-host&gt;" in html and "<your-host>" not in html
    context = build_context(scan, "REPORT-1", scan.created_at)
    assert context["findings"][0]["guide"]  # type: ignore[index]


def test_assessment_findings_all_resolve_to_guidance() -> None:
    headers = [h for h in GOOD_HEADERS if h[0] != "content-security-policy"]
    findings: list[Finding] = assess(page(headers), good_tls(), clean_probes()).findings
    assert findings and all(guidance_for(f.id) for f in findings)
