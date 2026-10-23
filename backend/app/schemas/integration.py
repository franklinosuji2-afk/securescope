"""API tokens and badges."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiTokenOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    created_by_email: str | None = None


class ApiTokenCreated(ApiTokenOut):
    # Shown once, when the token is made.
    token: str


class ApiTokenList(BaseModel):
    available: bool  # the plan includes CI access
    limit: int
    items: list[ApiTokenOut]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BadgeOut(BaseModel):
    target_id: str
    hostname: str
    enabled: bool
    # Only present while the badge is on.
    url: str | None = None


class BadgeList(BaseModel):
    items: list[BadgeOut]


class BadgeUpdate(BaseModel):
    enabled: bool
    # Renewing makes the old address stop working and gives a new one.
    renew: bool = False


class CiScanCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class CiFinding(BaseModel):
    id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str


class CiScanOut(BaseModel):
    id: str
    host: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    score: int | None = None
    grade: str | None = None
    counts: dict[str, int] = {}
    findings: list[CiFinding] = []
    error: str | None = None
    link: str
