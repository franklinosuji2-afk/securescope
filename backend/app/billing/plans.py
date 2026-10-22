"""The plan catalogue: what each plan includes. This is the only place plan limits are written down.

Prices and limits are starting hypotheses to be tested with real customers, so they live here as plain data and
nothing else in the code compares against a literal number or a plan name. A limit of None means no limit and
is used only by the internal plan, which no customer can buy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    price_eur_month: int
    max_websites: int | None
    scans_per_month: int | None
    history_days: int
    can_invite: bool
    purchasable: bool
    # Clients, agency dashboard, report branding and shared report links.
    client_workspace: bool = False
    # Scans that run on a schedule, with email alerts when something new appears.
    scheduled_scans: bool = False


FREE = Plan(
    "free", "Free", 0, max_websites=1, scans_per_month=3, history_days=30, can_invite=False, purchasable=False
)
PROFESSIONAL = Plan(
    "professional",
    "Professional",
    19,
    max_websites=5,
    scans_per_month=30,
    history_days=90,
    can_invite=False,
    purchasable=True,
    scheduled_scans=True,
)
AGENCY = Plan(
    "agency",
    "Agency",
    49,
    max_websites=20,
    scans_per_month=150,
    history_days=365,
    can_invite=True,
    purchasable=True,
    client_workspace=True,
    scheduled_scans=True,
)
# For the operator's own workspaces only. Assigned by the server, never offered to customers.
INTERNAL = Plan(
    "internal",
    "Internal",
    0,
    max_websites=None,
    scans_per_month=None,
    history_days=365,
    can_invite=True,
    purchasable=False,
    client_workspace=True,
    scheduled_scans=True,
)

PLANS: dict[str, Plan] = {plan.id: plan for plan in (FREE, PROFESSIONAL, AGENCY, INTERNAL)}
DEFAULT_PLAN_ID = FREE.id


def get_plan(plan_id: str | None) -> Plan:
    """An unknown or missing plan id falls back to Free, the most restrictive one a customer can have."""
    return PLANS.get(plan_id or DEFAULT_PLAN_ID, FREE)


def current_period(now: datetime) -> tuple[datetime, datetime]:
    """The calendar month (UTC) containing `now`: where monthly allowances start counting and reset.

    A billing provider's own period replaces this once subscriptions exist."""
    start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end
