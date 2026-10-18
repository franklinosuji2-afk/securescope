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


class Finding(BaseModel):
    id: str = Field(description="Stable identifier, e.g. SS-HDR-CSP-001")
    title: str
    severity: Severity
    category: str
    description: str
    evidence: str | None = Field(default=None, description="Safe, redacted evidence")
    remediation: str


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
