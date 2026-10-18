"""Report export. Every value is escaped for the output format."""

from __future__ import annotations

import html
import re

from app.schemas.scan import SEVERITY_ORDER, ScanDetail

DISCLAIMER = (
    "This report comes from a limited set of passive, non-exploitative checks and a heuristic "
    "score. An empty findings list is not proof of security, and this is not a penetration test."
)


def safe_filename(detail: ScanDetail, extension: str) -> str:
    host = re.sub(r"[^a-zA-Z0-9.-]", "-", detail.host)[:60] or "target"
    return f"securescope-{host}-{detail.created_at:%Y%m%d}.{extension}"


def _sorted_findings(detail: ScanDetail):  # type: ignore[no-untyped-def]
    order = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    return sorted(detail.findings, key=lambda f: (order[f.severity], f.id))


def to_json(detail: ScanDetail) -> str:
    return detail.model_dump_json(indent=2)


def _md(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>#|])", r"\\\1", text.replace("\n", " "))


def to_markdown(detail: ScanDetail) -> str:
    lines = [
        f"# SecureScope report: {_md(detail.host)}",
        "",
        f"- Target: {_md(detail.target_url)}",
        f"- Status: {detail.status.value}",
        f"- Scanned: {detail.created_at.isoformat(timespec='seconds')}",
    ]
    if detail.score is not None:
        lines.append(f"- Heuristic score: {detail.score}/100 (grade {detail.grade})")
    if detail.error:
        lines.append(f"- Error: {_md(detail.error)}")
    lines += ["", f"> {DISCLAIMER}", ""]
    if detail.counts:
        lines.append("## Summary")
        lines.append("")
        for severity in SEVERITY_ORDER:
            lines.append(f"- {severity.value.capitalize()}: {detail.counts.get(severity.value, 0)}")
        lines.append("")
    if detail.status.value == "completed":
        lines.append("## Findings")
        lines.append("")
        if not detail.findings:
            lines += ["No findings from the implemented checks.", ""]
        for finding in _sorted_findings(detail):
            lines += [
                f"### {_md(finding.title)} ({finding.severity.value})",
                "",
                f"- ID: {finding.id}",
                f"- Category: {_md(finding.category)}",
                f"- Description: {_md(finding.description)}",
            ]
            if finding.evidence:
                lines.append(f"- Evidence: {_md(finding.evidence)}")
            lines += [f"- Remediation: {_md(finding.remediation)}", ""]
    return "\n".join(lines).rstrip() + "\n"


def to_html(detail: ScanDetail) -> str:
    e = html.escape
    rows = []
    for finding in _sorted_findings(detail):
        evidence = f"<p><strong>Evidence:</strong> {e(finding.evidence)}</p>" if finding.evidence else ""
        rows.append(
            f'<section class="finding {e(finding.severity.value)}">'
            f'<h3>{e(finding.title)} <span class="badge">{e(finding.severity.value)}</span></h3>'
            f'<p class="meta">{e(finding.id)} · {e(finding.category)}</p>'
            f"<p>{e(finding.description)}</p>{evidence}"
            f"<p><strong>Remediation:</strong> {e(finding.remediation)}</p></section>"
        )
    score = (
        f'<p class="score">Heuristic score: <strong>{detail.score}/100</strong> (grade {e(detail.grade or "")})</p>'
        if detail.score is not None
        else ""
    )
    error = f'<p class="error">Error: {e(detail.error)}</p>' if detail.error else ""
    body = "".join(rows) if rows else "<p>No findings from the implemented checks.</p>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>SecureScope report: {e(detail.host)}</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#111}"
        ".finding{border:1px solid #ccd;border-radius:8px;padding:.5rem 1rem;margin:1rem 0}"
        ".badge{font-size:.75rem;text-transform:uppercase;border:1px solid currentColor;border-radius:99px;padding:0 .5rem}"
        ".meta{color:#556;font-size:.85rem}.note{background:#f4f1ff;border-left:4px solid #6d4aff;padding:.5rem 1rem}"
        ".critical,.high{border-color:#c0392b}.medium{border-color:#d68910}</style></head><body>"
        f"<h1>SecureScope report</h1><p>Target: {e(detail.target_url)}<br>"
        f"Scanned: {e(detail.created_at.isoformat(timespec='seconds'))}<br>Status: {e(detail.status.value)}</p>"
        f'{score}{error}<p class="note">{e(DISCLAIMER)}</p><h2>Findings</h2>{body}</body></html>'
    )
