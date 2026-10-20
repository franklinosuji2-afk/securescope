"""Report export. Every value is escaped for the output format."""

from __future__ import annotations

import html
import re
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Table, TableStyle

from app.scanner.checks import CHECK_LABELS, NOT_PASSED_AT_INFO
from app.schemas.scan import SEVERITY_ORDER, Finding, ScanDetail

DISCLAIMER = (
    "This report comes from a limited set of passive, non-exploitative checks and a heuristic "
    "score. An empty findings list is not proof of security, and this is not a penetration test."
)


LIMITS = (
    "Passive checks only: one page load of the address you scanned, plus any same-site redirects.",
    "Only the response headers and the start of the page were examined; other pages, forms and APIs were not.",
    "No login, no active testing, no vulnerability exploitation, no scan of subdomains.",
    "TLS: one verified connection is made to read the certificate and negotiated protocol. This is not a "
    "full TLS test: supported protocol versions, cipher suites and known TLS vulnerabilities are not scanned.",
    "Three fixed paths (/.well-known/security.txt, /.git/HEAD, /.env) are requested once each; "
    "no other paths are guessed or crawled.",
)


def coverage_notes(detail: ScanDetail) -> list[str]:
    """Plain-language lines about checks that could not run and what the TLS connection showed."""
    md = detail.metadata
    if md is None:
        return []
    notes = []
    for skipped in md.checks_skipped:
        label = CHECK_LABELS.get(skipped.name, (skipped.name, ()))[0]
        notes.append(f"Not checked: {label}. {skipped.reason}")
    tls = md.tls
    if tls is not None and tls.protocol:
        text = f"TLS: {tls.protocol}"
        if tls.days_remaining is not None:
            text += f"; certificate valid for {tls.days_remaining} more days"
        if tls.issuer:
            text += f"; issuer {tls.issuer}"
        notes.append(text + ".")
    return notes


def passed_checks(detail: ScanDetail) -> list[str]:
    """Human labels of checks that ran and raised nothing above informational level."""
    if detail.metadata is None:
        return []
    # An absent security.txt is only informational for the score, but the check has not passed.
    raised = {
        f.id for f in detail.findings if f.severity.value != "info" or f.id.startswith(NOT_PASSED_AT_INFO)
    }
    out = []
    for name in detail.metadata.checks_run:
        label, prefixes = CHECK_LABELS.get(name, (name, ()))
        if not any(i.startswith(prefixes) for i in raised if prefixes):
            out.append(label)
    return out


def _coverage_md(detail: ScanDetail) -> list[str]:
    md = detail.metadata
    if md is None or detail.status.value != "completed":
        return []
    lines = ["## What was checked", ""]
    lines.append(
        f"- Requests made: {md.requests_made}; final URL: {_md(md.final_url or md.requested_url)}; "
        f"HTTP status: {md.status_code}"
    )
    lines += [f"- Passed: {_md(label)}" for label in passed_checks(detail)]
    lines += [f"- {_md(note)}" for note in coverage_notes(detail)]
    lines += ["", "## Limits of this scan", ""]
    lines += [f"- {limit}" for limit in LIMITS]
    lines.append("")
    return lines


def safe_filename(detail: ScanDetail, extension: str) -> str:
    host = re.sub(r"[^a-zA-Z0-9.-]", "-", detail.host)[:60] or "target"
    return f"securescope-{host}-{detail.created_at:%Y%m%d}.{extension}"


def _sorted_findings(detail: ScanDetail):  # type: ignore[no-untyped-def]
    order = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    return sorted(detail.findings, key=lambda f: (order[f.severity], f.id))


def _status_label(finding: Finding) -> str:
    status = finding.status.value
    if status == "open":
        first, last = finding.first_seen_at, finding.last_seen_at
        if first and last and first != last:
            return f"Open (first seen {first:%Y-%m-%d %H:%M} UTC, last seen {last:%Y-%m-%d %H:%M} UTC)"
        if first:
            return f"Open (seen in one scan so far, {first:%Y-%m-%d %H:%M} UTC)"
        return "Open"
    return {
        "accepted_risk": "Accepted risk",
        "false_positive": "Marked false positive",
        "resolved": "Resolved (a later scan no longer reported it)",
    }.get(status, status)


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
                f"- Confidence: {finding.confidence.value}",
                f"- Status: {_status_label(finding)}",
                f"- Description: {_md(finding.description)}",
            ]
            if finding.evidence:
                lines.append(f"- Evidence: {_md(finding.evidence)}")
            lines += [f"- Remediation: {_md(finding.remediation)}", ""]
    lines += _coverage_md(detail)
    return "\n".join(lines).rstrip() + "\n"


def to_html(detail: ScanDetail) -> str:
    e = html.escape
    rows = []
    for finding in _sorted_findings(detail):
        evidence = f"<p><strong>Evidence:</strong> {e(finding.evidence)}</p>" if finding.evidence else ""
        rows.append(
            f'<section class="finding {e(finding.severity.value)}">'
            f'<h3>{e(finding.title)} <span class="badge">{e(finding.severity.value)}</span></h3>'
            f'<p class="meta">{e(finding.id)} · {e(finding.category)} · confidence {e(finding.confidence.value)}'
            f" · {e(_status_label(finding))}</p>"
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
    if detail.metadata is not None and detail.status.value == "completed":
        md = detail.metadata
        passed = "".join(f"<li>{e(label)}</li>" for label in passed_checks(detail))
        passed += "".join(f"<li>{e(note)}</li>" for note in coverage_notes(detail))
        limits = "".join(f"<li>{e(limit)}</li>" for limit in LIMITS)
        body += (
            "<h2>What was checked</h2>"
            f"<p>Requests made: {md.requests_made}. Final URL: {e(md.final_url or md.requested_url)}. "
            f"HTTP status: {md.status_code}.</p><p>Passed:</p><ul>{passed}</ul>"
            f"<h2>Limits of this scan</h2><ul>{limits}</ul>"
        )
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


# --- PDF ---------------------------------------------------------------------------------------------

_SEVERITY_COLOUR = {
    "critical": "#8e1b1b",
    "high": "#b3261e",
    "medium": "#8a5a00",
    "low": "#0b5cad",
    "info": "#44505c",
}


def _pdf_text(value: str) -> str:
    """Makes untrusted text safe for a PDF paragraph.

    Evidence can contain anything a remote server sent. Control characters are dropped, markup is
    escaped (reportlab paragraphs are a small XML dialect), and characters outside the built-in
    fonts' Latin range become "?" instead of boxes.
    """
    visible = "".join(ch for ch in value if ch == "\n" or (ch >= " " and ch != "\x7f"))
    latin = visible.encode("cp1252", "replace").decode("cp1252")
    return html.escape(latin, quote=False).replace("\n", " ")


def _pdf_styles() -> dict[str, ParagraphStyle]:
    # wordWrap="CJK" lets a long unbroken value (a URL, a header) wrap instead of running off the page.
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13.5, wordWrap="CJK")
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=12, spaceAfter=4
        ),
        "h3": ParagraphStyle(
            "h3", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, keepWithNext=1
        ),
        "meta": ParagraphStyle("meta", parent=base, fontSize=8.5, textColor=colors.HexColor("#4a5560"), keepWithNext=1),
        "note": ParagraphStyle(
            "note", parent=base, backColor=colors.HexColor("#f1eefc"), borderPadding=6, spaceBefore=8, spaceAfter=8
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base,
            fontName="Courier",
            fontSize=8.5,
            leading=11.5,
            backColor=colors.HexColor("#f2f4f6"),
            borderPadding=4,
            spaceBefore=3,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2),
    }


def to_pdf(detail: ScanDetail) -> bytes:
    """A printable report with the same content as the HTML export."""
    st = _pdf_styles()
    t = _pdf_text
    story: list[Any] = [
        Paragraph("SecureScope report", st["title"]),
        Paragraph(t(detail.host), st["h2"]),
    ]
    rows = [
        ["Target", t(detail.target_url)],
        ["Scanned", f"{detail.created_at:%Y-%m-%d %H:%M} UTC"],
        ["Status", t(detail.status.value)],
    ]
    if detail.score is not None:
        rows.append(["Heuristic score", f"{detail.score}/100 (grade {t(detail.grade or '')})"])
    if detail.error:
        rows.append(["Error", t(detail.error)])
    table = Table(
        [[Paragraph(f"<b>{label}</b>", st["base"]), Paragraph(value, st["base"])] for label, value in rows],
        colWidths=[32 * mm, 138 * mm],
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story += [table, Paragraph(t(DISCLAIMER), st["note"])]

    if detail.counts:
        summary = ", ".join(
            f"{severity.value.capitalize()} {detail.counts.get(severity.value, 0)}" for severity in SEVERITY_ORDER
        )
        story.append(Paragraph(f"<b>Findings by severity:</b> {summary}", st["base"]))

    if detail.status.value == "completed":
        story.append(Paragraph("Findings", st["h2"]))
        if not detail.findings:
            story.append(Paragraph("No findings from the implemented checks.", st["base"]))
        for finding in _sorted_findings(detail):
            colour = _SEVERITY_COLOUR.get(finding.severity.value, "#000000")
            block: list[Any] = [
                Paragraph(
                    f'{t(finding.title)} <font color="{colour}" size="9">[{t(finding.severity.value.upper())}]</font>',
                    st["h3"],
                ),
                Paragraph(
                    f"{t(finding.id)} · {t(finding.category)} · confidence {t(finding.confidence.value)} · "
                    f"{t(_status_label(finding))}",
                    st["meta"],
                ),
                Paragraph(t(finding.description), st["base"]),
            ]
            if finding.evidence:
                block += [Paragraph("<b>Evidence</b>", st["base"]), Paragraph(t(finding.evidence), st["mono"])]
            block.append(Paragraph(f"<b>Remediation:</b> {t(finding.remediation)}", st["base"]))
            story.append(KeepTogether(block[:3]))
            story += block[3:]

        md = detail.metadata
        if md is not None:
            story.append(Paragraph("What was checked", st["h2"]))
            story.append(
                Paragraph(
                    f"Requests made: {md.requests_made}. Final URL: {t(md.final_url or md.requested_url)}. "
                    f"HTTP status: {md.status_code}.",
                    st["base"],
                )
            )
            story.append(Paragraph("Passed:", st["base"]))
            story += [Paragraph(t(label), st["bullet"], bulletText="•") for label in passed_checks(detail)]
            story += [Paragraph(t(note), st["bullet"], bulletText="•") for note in coverage_notes(detail)]
            story.append(Paragraph("Limits of this scan", st["h2"]))
            story += [Paragraph(t(limit), st["bullet"], bulletText="•") for limit in LIMITS]

    host_label = t(detail.host)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4a5560"))
        canvas.drawString(20 * mm, 10 * mm, f"SecureScope · {html.unescape(host_label)}")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"SecureScope report: {detail.host}".encode("cp1252", "replace").decode("cp1252"),
        author="SecureScope",
        creator="SecureScope",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
