"""Which plan applies, given a subscription. Pure functions: no database, no clock, no provider.

The rule, in plain words:
- The internal plan (the operator's own workspaces) is never changed by a subscription.
- An organization with no subscription keeps whatever plan it already has (Free unless one was assigned).
- A paid subscription gives its plan while the paid period lasts. That includes a subscription that was cancelled
  or is behind on payment: what was paid for stays until the period ends, and not a day longer.
- After the period ends, a requested downgrade (`pending_plan_id`) starts; otherwise the organization goes back
  to the plan it had before (Free by default).
- Nothing here deletes anything. Going to a lower plan only stops new additions beyond its limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.billing.plans import INTERNAL, PLANS

ACTIVE = "active"
PAST_DUE = "past_due"
CANCELED = "canceled"
STATUSES = frozenset({ACTIVE, PAST_DUE, CANCELED})


@dataclass(frozen=True, slots=True)
class SubscriptionState:
    provider: str
    plan_id: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    pending_plan_id: str | None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def paid_period_open(sub: SubscriptionState, now: datetime) -> bool:
    """Is the customer still inside what they paid for?"""
    if sub.current_period_end is not None:
        return _aware(now) < _aware(sub.current_period_end)
    # No end date known: only an active subscription that is not set to end counts.
    return sub.status == ACTIVE and not sub.cancel_at_period_end


def effective_plan_id(base_plan_id: str | None, sub: SubscriptionState | None, now: datetime) -> str | None:
    """The plan id that applies now, or None for "the default plan"."""
    if base_plan_id == INTERNAL.id or sub is None or sub.status not in STATUSES:
        return base_plan_id
    if sub.plan_id not in PLANS or not PLANS[sub.plan_id].purchasable:
        return base_plan_id
    if paid_period_open(sub, now):
        return sub.plan_id
    if sub.pending_plan_id in PLANS and sub.status == ACTIVE and sub.pending_plan_id != INTERNAL.id:
        return sub.pending_plan_id
    return base_plan_id
