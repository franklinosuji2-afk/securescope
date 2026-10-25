"""Whatever a subscription row says, it can never give more than was paid for, take away the operator's own plan,
or keep paid access after the paid period ended. Every combination is tried, not a handful of examples."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from app.billing.lifecycle import STATUSES, SubscriptionState, effective_plan_id
from app.billing.plans import INTERNAL, PLANS

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
PLAN_IDS = [None, "free", "professional", "agency", "internal", "bogus", ""]
STATUS_VALUES = [*sorted(STATUSES), "bogus", ""]
ENDS = [
    None,
    NOW - timedelta(days=30),
    NOW - timedelta(seconds=1),
    NOW,
    NOW + timedelta(seconds=1),
    NOW + timedelta(days=30),
]
PENDING = [None, "free", "professional", "agency", "internal", "bogus"]


def cases() -> Iterator[tuple[str | None, SubscriptionState]]:
    for base, plan, status, end, cancel, pending in itertools.product(
        PLAN_IDS, PLAN_IDS[1:], STATUS_VALUES, ENDS, (False, True), PENDING
    ):
        yield base, SubscriptionState("test", plan or "", status, end, cancel, pending)


def test_there_are_enough_combinations_to_mean_something() -> None:
    assert sum(1 for _ in cases()) > 5000


def test_the_result_is_always_a_known_plan_or_the_default() -> None:
    for base, sub in cases():
        result = effective_plan_id(base, sub, NOW)
        assert result is None or result in PLANS or result == base, (base, sub, result)


def test_the_result_only_ever_comes_from_the_workspace_the_subscription_or_its_requested_downgrade() -> None:
    for base, sub in cases():
        result = effective_plan_id(base, sub, NOW)
        assert result in (base, sub.plan_id, sub.pending_plan_id), (base, sub, result)


def test_the_internal_plan_is_never_given_by_a_subscription_nor_taken_by_one() -> None:
    for base, sub in cases():
        result = effective_plan_id(base, sub, NOW)
        if base == INTERNAL.id:
            assert result == INTERNAL.id, (base, sub, result)
        else:
            assert result != INTERNAL.id, (base, sub, result)


def test_only_a_plan_that_can_be_bought_is_ever_granted_by_a_subscription() -> None:
    for base, sub in cases():
        result = effective_plan_id(base, sub, NOW)
        if result == sub.plan_id and result != base:
            assert result in PLANS and PLANS[result].purchasable, (base, sub, result)


def test_an_unknown_status_changes_nothing() -> None:
    for base, sub in cases():
        if sub.status not in STATUSES:
            assert effective_plan_id(base, sub, NOW) == base, (base, sub)


def test_paid_access_never_outlives_the_paid_period_unless_the_subscription_is_active_and_asked_for_a_downgrade() -> (
    None
):
    for base, sub in cases():
        if base == INTERNAL.id or sub.status not in STATUSES or sub.current_period_end is None:
            continue
        if sub.current_period_end > NOW:
            continue
        result = effective_plan_id(base, sub, NOW)
        # After the end, what is left is the workspace's own plan, or the downgrade the customer asked for.
        allowed = {base}
        if sub.status == "active" and sub.pending_plan_id in PLANS and sub.pending_plan_id != INTERNAL.id:
            allowed.add(sub.pending_plan_id)
        assert result in allowed, (base, sub, result)


def test_once_the_period_is_over_the_answer_does_not_change_as_time_passes() -> None:
    for base, sub in cases():
        if sub.current_period_end is None or sub.current_period_end > NOW:
            continue
        answers = {effective_plan_id(base, sub, NOW + timedelta(days=d)) for d in (0, 1, 30, 400)}
        assert len(answers) == 1, (base, sub, answers)


def test_a_subscription_without_an_end_date_counts_only_while_active_and_not_ending() -> None:
    for base in PLAN_IDS:
        for status, cancel in itertools.product(STATUS_VALUES, (False, True)):
            sub = SubscriptionState("test", "professional", status, None, cancel, None)
            result = effective_plan_id(base, sub, NOW)
            if base != INTERNAL.id and status == "active" and not cancel:
                assert result == "professional"
            else:
                assert result == base


def test_a_missing_subscription_never_changes_the_plan() -> None:
    for base in PLAN_IDS:
        assert effective_plan_id(base, None, NOW) == base
