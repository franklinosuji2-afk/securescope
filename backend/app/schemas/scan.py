"""Typed request and response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Confidence(StrEnum):
    """How sure the check is that the finding is real. Direct observations of a response are HIGH."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingStatus(StrEnum):
    """Per-organization, per-host state of a finding.

    OPEN, ACCEPTED_RISK and FALSE_POSITIVE can be set by an analyst. RESOLVED is only ever set by the
    system, when a later completed scan of the same host no longer reports the finding.
    """

    OPEN = "open"
    ACCEPTED_RISK = "accepted_risk"
    FALSE_POSITIVE = "false_positive"
    RESOLVED = "resolved"


ANALYST_STATUSES: tuple[FindingStatus, ...] = (
    FindingStatus.OPEN,
    FindingStatus.ACCEPTED_RISK,
    FindingStatus.FALSE_POSITIVE,
)


class Finding(BaseModel):
    id: str = Field(description="Stable identifier, e.g. SS-HDR-CSP-001")
    title: str
    severity: Severity
    category: str
    description: str
    evidence: str | None = Field(default=None, description="Safe, redacted evidence")
    remediation: str
    confidence: Confidence = Confidence.HIGH
    # Filled in when a scan is stored or read back; checks never set these.
    fingerprint: str | None = Field(default=None, description="Stable id of this finding on this host")
    status: FindingStatus = FindingStatus.OPEN
    status_note: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class FindingStatusUpdate(BaseModel):
    status: FindingStatus
    note: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def analyst_status_only(cls, value: FindingStatus) -> FindingStatus:
        if value not in ANALYST_STATUSES:
            raise ValueError("Only the scanner can mark a finding as resolved.")
        return value

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None


class TargetMetadata(BaseModel):
    requested_url: str
    final_url: str | None = None
    host: str
    resolved_addresses: list[str] = []
    status_code: int | None = None
    content_type: str | None = None
    redirect_chain: list[str] = []
    off_origin_redirect: str | None = None
    response_time_ms: int | None = None
    requests_made: int = 0
    checks_run: list[str] = []


class ScanCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    authorization_confirmed: bool = Field(
        description="The requester confirms they own the target or have written authorization."
    )

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        return value.strip()


class ScanSummary(BaseModel):
    id: str
    target_url: str
    host: str
    status: ScanStatus
    score: int | None = None
    grade: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    counts: dict[str, int] = {}


class ScanDetail(ScanSummary):
    error: str | None = None
    metadata: TargetMetadata | None = None
    findings: list[Finding] = []
    score_note: str = (
        "Heuristic score based on a small set of passive checks. A high score or an empty "
        "findings list is not proof that a site is secure and is not a penetration test."
    )


class ScanList(BaseModel):
    items: list[ScanSummary]
    total: int


class ErrorBody(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
