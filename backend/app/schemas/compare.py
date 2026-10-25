"""What changed between two scans of the same site."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.scan import Finding, ScanStatus


class ComparedScan(BaseModel):
    id: str
    scanned_at: datetime
    status: ScanStatus
    score: int | None = None
    grade: str | None = None


class ScanComparison(BaseModel):
    host: str
    older: ComparedScan
    newer: ComparedScan
    score_change: int | None = None
    new_findings: list[Finding]
    resolved_findings: list[Finding]
    unchanged_findings: list[Finding]
    # Findings that appear in only one scan because a check did not run in the other. They are neither new
    # nor resolved: the comparison cannot tell.
    not_comparable_findings: list[Finding] = []
    # Plain-language names of the checks that did not run in either scan.
    not_comparable_checks: list[str] = []
    note: str
