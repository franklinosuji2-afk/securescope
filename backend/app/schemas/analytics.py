"""Analytics requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Page = Literal[
    "home",
    "login",
    "register",
    "forgot-password",
    "reset-password",
    "verify-email",
    "sample-report",
    "impressum",
    "privacy",
    "terms",
]


class CollectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: Page
    referrer: str | None = Field(default=None, max_length=512)


class DayPoint(BaseModel):
    date: str
    views: int
    visitors: int


class Period(BaseModel):
    views: int
    visitors: int
    series: list[DayPoint]


class Totals(BaseModel):
    views: int
    visitors: int


class NamedCount(BaseModel):
    name: str
    count: int


class PageCount(NamedCount):
    visitors: int


class AnalyticsSummary(BaseModel):
    range_days: int
    timezone: str
    tracking_enabled: bool
    last_event_at: datetime | None
    current: Period
    previous: Period
    today: Totals
    yesterday: Totals
    top_pages: list[PageCount]
    landing_pages: list[NamedCount]
    sources: list[NamedCount]
    devices: list[NamedCount]
