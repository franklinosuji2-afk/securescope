"""One place that answers "what may this organization do?" Enforcement code calls this and nothing else."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from app.billing.lifecycle import effective_plan_id
from app.billing.plans import Plan, current_period, get_plan
from app.repositories.billing import BillingRepository
from app.repositories.plans import PlanRepository


@dataclass(frozen=True, slots=True)
class PlanSummary:
    plan: Plan
    websites_used: int
    scans_used: int
    period_start: datetime
    period_end: datetime


class Entitlements:
    def __init__(
        self,
        plans: PlanRepository,
        default_plan_id: str | None = None,
        billing: BillingRepository | None = None,
    ) -> None:
        self._plans = plans
        self._default = default_plan_id
        self._billing = billing

    def plan_for(self, organization_id: str) -> Plan:
        base = self._plans.plan_id(organization_id) or self._default
        sub = self._billing.subscription(organization_id) if self._billing else None
        return get_plan(effective_plan_id(base, sub, datetime.now(UTC)))

    def summary(self, organization_id: str) -> PlanSummary:
        start, end = current_period(datetime.now(UTC))
        websites, scans = self._plans.usage(organization_id, start)
        return PlanSummary(self.plan_for(organization_id), websites, scans, start, end)

    async def plan_for_async(self, organization_id: str) -> Plan:
        return await asyncio.to_thread(self.plan_for, organization_id)
