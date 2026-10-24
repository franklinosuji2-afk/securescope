from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlanLimits(BaseModel):
    websites: int | None
    scans_per_month: int | None
    history_days: int
    can_invite: bool
    client_workspace: bool = False
    scheduled_scans: bool = False


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
    subscription: SubscriptionOut | None = None


class SubscriptionOut(BaseModel):
    status: str
    plan_id: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    pending_plan_id: str | None


class DowngradeEffectOut(BaseModel):
    key: str
    kind: str
    message: str
    used: int
    limit: int | None


class DowngradePreview(BaseModel):
    """What moving to a lower plan would change. Nothing is changed or deleted by asking."""

    current_plan_id: str
    target_plan_id: str
    target_name: str
    effects: list[DowngradeEffectOut]
    deletes_nothing_now: bool = True
