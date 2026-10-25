"""Subscription state, handled provider events, and the counts behind the downgrade preview."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError

from app.billing.lifecycle import SubscriptionState
from app.database.session import make_session_factory
from app.models.account import InvitationRow, MemberRow
from app.models.agency import ClientRow
from app.models.billing import BillingEventRow, SubscriptionRow
from app.models.integration import ApiTokenRow
from app.models.scan import ScanRow
from app.models.schedule import ScanScheduleRow
from app.models.target import TargetRow
from app.schemas.scan import ScanStatus


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class PlanUsage:
    """What an organization currently has, counted for the downgrade preview."""

    websites: int
    scans_this_month: int
    scans_older_than_history: int
    schedules: int
    api_tokens: int
    clients: int
    members: int
    pending_invitations: int


def state_from_row(row: SubscriptionRow) -> SubscriptionState:
    return SubscriptionState(
        provider=row.provider,
        plan_id=row.plan_id,
        status=row.status,
        current_period_end=row.current_period_end,
        cancel_at_period_end=bool(row.cancel_at_period_end),
        pending_plan_id=row.pending_plan_id,
    )


class BillingRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def subscription(self, organization_id: str) -> SubscriptionState | None:
        with self._session() as session:
            row = session.get(SubscriptionRow, organization_id)
            return state_from_row(row) if row else None

    def save_subscription(
        self, organization_id: str, provider_subscription_id: str, state: SubscriptionState
    ) -> None:
        """Creates or replaces the organization's subscription. Called only after a provider event has been
        verified; nothing in the app calls it until a provider is connected."""
        now = _now()
        with self._session.begin() as session:
            row = session.get(SubscriptionRow, organization_id)
            if row is None:
                row = SubscriptionRow(
                    organization_id=organization_id,
                    provider=state.provider,
                    provider_subscription_id=provider_subscription_id,
                    created_at=now,
                    plan_id=state.plan_id,
                    status=state.status,
                    updated_at=now,
                )
                session.add(row)
            row.provider = state.provider
            row.provider_subscription_id = provider_subscription_id
            row.plan_id = state.plan_id
            row.status = state.status
            row.current_period_end = state.current_period_end
            row.cancel_at_period_end = state.cancel_at_period_end
            row.pending_plan_id = state.pending_plan_id
            row.updated_at = now

    def record_event(
        self, provider: str, provider_event_id: str, event_type: str, organization_id: str | None
    ) -> bool:
        """True the first time an event id is seen, False for every repeat. Callers apply an event's effect
        only when this returns True."""
        try:
            with self._session.begin() as session:
                session.add(
                    BillingEventRow(
                        id=uuid.uuid4().hex,
                        provider=provider,
                        provider_event_id=provider_event_id,
                        event_type=event_type,
                        organization_id=organization_id,
                        received_at=_now(),
                    )
                )
        except IntegrityError:
            return False
        return True

    def usage(self, organization_id: str, period_start: datetime, history_days: int) -> PlanUsage:
        cutoff = _now() - timedelta(days=history_days)
        with self._session() as session:

            def count(stmt) -> int:  # type: ignore[no-untyped-def]
                return int(session.scalar(stmt) or 0)

            return PlanUsage(
                websites=count(
                    select(func.count())
                    .select_from(TargetRow)
                    .where(TargetRow.organization_id == organization_id)
                ),
                scans_this_month=count(
                    select(func.count())
                    .select_from(ScanRow)
                    .where(
                        ScanRow.organization_id == organization_id,
                        ScanRow.created_at >= period_start,
                        ScanRow.status != ScanStatus.FAILED.value,
                    )
                ),
                scans_older_than_history=count(
                    select(func.count())
                    .select_from(ScanRow)
                    .where(ScanRow.organization_id == organization_id, ScanRow.created_at < cutoff)
                ),
                schedules=count(
                    select(func.count())
                    .select_from(ScanScheduleRow)
                    .where(
                        ScanScheduleRow.organization_id == organization_id,
                        ScanScheduleRow.frequency != "off",
                    )
                ),
                api_tokens=count(
                    select(func.count())
                    .select_from(ApiTokenRow)
                    .where(ApiTokenRow.organization_id == organization_id, ApiTokenRow.revoked_at.is_(None))
                ),
                clients=count(
                    select(func.count())
                    .select_from(ClientRow)
                    .where(ClientRow.organization_id == organization_id)
                ),
                members=count(
                    select(func.count())
                    .select_from(MemberRow)
                    .where(MemberRow.organization_id == organization_id)
                ),
                pending_invitations=count(_pending_invitations(organization_id)),
            )


def _pending_invitations(organization_id: str):  # type: ignore[no-untyped-def]
    return (
        select(func.count())
        .select_from(InvitationRow)
        .where(
            InvitationRow.organization_id == organization_id,
            InvitationRow.accepted_at.is_(None),
            InvitationRow.revoked_at.is_(None),
            InvitationRow.expires_at > _now(),
        )
    )
