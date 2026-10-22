from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlanLimits(BaseModel):
    websites: int | None
    scans_per_month: int | None
    history_days: int
    can_invite: bool


class PlanUsage(BaseModel):
    websites: int
    scans_this_period: int
    period_start: datetime
    period_end: datetime


class PlanOut(BaseModel):
    plan_id: str
    name: str
    price_eur_month: int
    limits: PlanLimits
    usage: PlanUsage
