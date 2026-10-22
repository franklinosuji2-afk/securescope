"""Scheduled scans."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScheduleOut(BaseModel):
    target_id: str
    hostname: str
    frequency: Literal["off", "daily", "weekly"]
    url: str
    notify: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_scan_id: str | None = None
    last_outcome: str | None = None


class ScheduleList(BaseModel):
    available: bool
    items: list[ScheduleOut]


class ScheduleUpdate(BaseModel):
    frequency: Literal["off", "daily", "weekly"]
    notify: bool = True
    # Optional: the address to scan. It defaults to https://<site>/ and its host must be the verified site.
    url: str | None = Field(default=None, max_length=2048)


class RunSummary(BaseModel):
    due: int
    scans_started: int
    alerts_sent: int
    skipped: int
