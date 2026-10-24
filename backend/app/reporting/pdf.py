"""Client PDF reports: a clean HTML template rendered to PDF on the server (WeasyPrint).

Every scan value is passed to the template as data and escaped by Jinja's autoescaping, so text that a
scanned site sent (headers, cookies, page content) can never become markup. The renderer is also not
allowed to fetch anything: no remote images, stylesheets or fonts, whatever the text contains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.reporting.guidance import guidance_for
from app.reporting.reports import DISCLAIMER, LIMITS, coverage_notes, passed_checks
from app.reporting.risk import RiskRating, counting_findings, overall_risk, severity_counts
from app.scanner.scoring import method_lines, score_note
from app.schemas.scan import SEVERITY_ORDER, Finding, FindingStatus, ScanDetail

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

SEVERITY_COLOUR = {
    "critical": "#8e1b1b",
    "high": "#b3261e",
    "medium": "#9a6200",
    "low": "#0b5cad",
    "info": "#44505c",
}
RISK_COLOUR = {
    "critical": "#8e1b1b",
    "high": "#b3261e",
    "medium": "#9a6200",
    "low": "#0b5cad",
    "minimal": "#1e7a46",
}
SEVERITY_LABEL = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Information",
}
_PATH_FOR_FINDING = {
    "SS-EXPOSE-GIT-": "/.git/HEAD",
    "SS-EXPOSE-ENV-": "/.env",
    "SS-DISC-SEC-": "/.well-known/security.txt",
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class RenderedReport:
    report_id: str
    content: bytes


def _clean(value: str) -> str:
    """Drops control characters that can break a document; the template escapes everything else."""
    return _CONTROL.sub("", value)


def affected_url(detail: ScanDetail, finding: Finding) -> str:
    base = detail.metadata.final_url if detail.metadata and detail.metadata.final_url else detail.target_url
    for prefix, path in _PATH_FOR_FINDING.items():
        if finding.id.startswith(prefix):
            parts = urlsplit(base)
            return f"{parts.scheme}://{parts.netloc}{path}"
    return base


def _dns_name(detail: ScanDetail) -> str:
    host = detail.host.lower().rstrip(".")
    return f"DNS records of {host.removeprefix('www.')}"


def _status_label(finding: Finding) -> str:
    return {
        FindingStatus.OPEN: "",
        FindingStatus.ACCEPTED_RISK: "Accepted risk",
        FindingStatus.FALSE_POSITIVE: "Marked as false positive",
        FindingStatus.RESOLVED: "No longer detected",
    }.get(finding.status, "")


def _guidance_context(finding: Finding) -> dict[str, object] | None:
    """Static guidance for the finding type, cleaned like every other value. Platform examples are capped."""
    guide = guidance_for(finding.id)
    if guide is None:
        return None
    return {
        "impact": _clean(guide.impact),
        "fixes": [{"label": _clean(x.label), "code": _clean(x.code)} for x in guide.fixes[:3]],
        "verify": [_clean(step) for step in guide.verify],
    }


def _ordered(detail: ScanDetail) -> list[Finding]:
    rank = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    return sorted(counting_findings(detail), key=lambda f: (rank[f.severity], f.id))


def build_context(
    detail: ScanDetail,
    report_id: str,
    generated_at: datetime,
    prepared_by: str | None = None,
    sample: bool = False,
) -> dict[str, object]:
    risk: RiskRating = overall_risk(detail)
    counts = severity_counts(detail)
    ordered = _ordered(detail)
    findings = [
        {
            "id": _clean(f.id),
            "title": _clean(f.title),
            "severity": f.severity.value,
            "severity_label": SEVERITY_LABEL[f.severity.value],
            "category": _clean(f.category),
            "description": _clean(f.description),
            "evidence": _clean(f.evidence) if f.evidence else None,
            "remediation": _clean(f.remediation),
            "url": _clean(affected_url(detail, f)),
            # DNS findings are about the domain's records, not a page, so the report says that.
            "where_label": "Affected records" if f.id.startswith("SS-DNS-") else "Affected URL",
            "where": _clean(_dns_name(detail))
            if f.id.startswith("SS-DNS-")
            else _clean(affected_url(detail, f)),
            "status_label": _status_label(f),
            "guide": _guidance_context(f),
        }
        for f in ordered
    ]
    seen: set[str] = set()
    plan = []
    for item in findings:  # the same fix is listed once, most severe first
        key = str(item["title"])
        if key not in seen:
            seen.add(key)
            plan.append(item)
    return {
        "report_id": report_id,
        "sample": sample,  # the public example report: says so on the cover and in the footer
        "prepared_by": _clean(prepared_by) if prepared_by else None,
        "host": _clean(detail.host),
        "target_url": _clean(detail.target_url),
        "scan_date": f"{detail.created_at:%d %B %Y, %H:%M} UTC",
        "generated_at": f"{generated_at:%d %B %Y, %H:%M} UTC",
        "risk": risk,
        "risk_colour": RISK_COLOUR[risk.level],
        "score": detail.score,
        "grade": detail.grade,
        "score_note": score_note(detail.findings, detail.score) if detail.score is not None else None,
        "score_method": method_lines(),
        "severity_rows": [
            {"label": SEVERITY_LABEL[s.value], "count": counts[s.value], "colour": SEVERITY_COLOUR[s.value]}
            for s in SEVERITY_ORDER
        ],
        "findings": findings,
        "plan": plan,
        "passed": [_clean(x) for x in passed_checks(detail)],
        "coverage": [_clean(x) for x in coverage_notes(detail)],
        "limits": list(LIMITS),
        "disclaimer": DISCLAIMER,
    }


def render_html(
    detail: ScanDetail,
    report_id: str,
    generated_at: datetime | None = None,
    prepared_by: str | None = None,
    sample: bool = False,
) -> str:
    context = build_context(detail, report_id, generated_at or datetime.now(UTC), prepared_by, sample)
    return _env.get_template("report.html").render(**context)


def _refuse_fetch(url: str, *args: object, **kwargs: object) -> dict[str, object]:
    raise ValueError(f"Report rendering may not load external resources: {url[:80]}")


def render_pdf(
    detail: ScanDetail,
    report_id: str,
    generated_at: datetime | None = None,
    prepared_by: str | None = None,
    sample: bool = False,
) -> RenderedReport:
    # Imported here so the rest of the API (and its tests) start without the PDF libraries' native code.
    from weasyprint import HTML

    html_text = render_html(detail, report_id, generated_at, prepared_by, sample)
    content = HTML(string=html_text, url_fetcher=_refuse_fetch).write_pdf()
    return RenderedReport(report_id, content)
