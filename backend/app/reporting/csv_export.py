"""CSV export of one scan's findings.

Spreadsheet programs run text that starts with = + - @ (or a tab or carriage return) as a formula. Scan
values include text that came from a website, so every cell is neutralised with a leading apostrophe.
"""

from __future__ import annotations

import csv
import io

from app.reporting.pdf import affected_url
from app.schemas.scan import ScanDetail

HEADER = (
    "scan_id",
    "scanned_at",
    "host",
    "finding_id",
    "severity",
    "status",
    "confidence",
    "title",
    "category",
    "affected_url",
    "description",
    "remediation",
)
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_DANGEROUS) else text


def to_csv(detail: ScanDetail) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADER)
    for f in detail.findings:
        writer.writerow(
            [
                safe_cell(v)
                for v in (
                    detail.id,
                    detail.created_at.isoformat(),
                    detail.host,
                    f.id,
                    f.severity.value,
                    f.status.value,
                    f.confidence.value,
                    f.title,
                    f.category,
                    affected_url(detail, f),
                    f.description,
                    f.remediation,
                )
            ]
        )
    return out.getvalue()
