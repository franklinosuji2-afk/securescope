"""App Scanning request and response shapes. There is deliberately no score or grade anywhere in them."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class AppProjectOut(BaseModel):
    id: str
    name: str
    source: str
    created_at: datetime


class AppProjectList(BaseModel):
    items: list[AppProjectOut]


class AppFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    content: str = Field(max_length=2_100_000)


class AppScanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9]+$")
    files: list[AppFileIn] = Field(min_length=1, max_length=5)
    kinds: list[Literal["dependency"]] = Field(default=["dependency"], min_length=1, max_length=1)
    ref: str | None = Field(default=None, max_length=120)


ResultLabel = Literal[
    "queued",
    "running",
    "completed_findings",
    "completed_no_findings",
    "incomplete",
    "scanner_error",
    "interrupted",
    "cancelled",
]


class AppFindingOut(BaseModel):
    kind: str
    rule_id: str
    title: str
    severity: str
    confidence: str
    category: str
    description: str
    remediation: str
    evidence: str | None
    path: str | None
    line: int | None
    ecosystem: str | None
    package_name: str | None
    package_version: str | None
    fixed_versions: list[str]
    references: list[str]
    aliases: list[str]
    fingerprint: str


class AppInputOut(BaseModel):
    name: str
    size: int
    sha256: str


class AppScanOut(BaseModel):
    id: str
    project_id: str
    status: str
    result: ResultLabel
    result_text: str
    kinds: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    inputs: list[AppInputOut]
    checks_run: list[str]
    checks_skipped: list[dict[str, str]]
    scanners: list[dict[str, str]]
    error: str | None
    counts: dict[str, int]
    findings: list[AppFindingOut]
    limitations: list[str]
    replayed: bool = False


class AppScanSummary(BaseModel):
    id: str
    project_id: str
    status: str
    result: ResultLabel
    result_text: str
    created_at: datetime
    finished_at: datetime | None
    counts: dict[str, int]


class AppScanList(BaseModel):
    items: list[AppScanSummary]


class AppUsageOut(BaseModel):
    runs_used: int
    runs_limit: int | None
    projects_used: int
    projects_limit: int | None
    period_end: datetime


class AppOverview(BaseModel):
    plan: str
    usage: AppUsageOut
    supported_files: list[str]
    max_files: int
    max_file_bytes: int
    ci_tokens_available: bool
    limitations: list[str]
