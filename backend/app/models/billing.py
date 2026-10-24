"""Which plan an organization is on. No row means the default plan."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class OrganizationPlanRow(Base):
    __tablename__ = "organization_plans"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(String(32))
    # Who set it: "system" for the operator's own workspaces, later the billing provider.
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SubscriptionRow(Base):
    """A paid subscription as the billing provider reports it. At most one per organization.

    Nothing writes this table until a billing provider is connected; the entitlement rule reads it so that the
    rule is tested before real money depends on it. Only identifiers and dates are stored, never card or
    customer details."""

    __tablename__ = "subscriptions"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    provider_subscription_id: Mapped[str] = mapped_column(String(64))
    plan_id: Mapped[str] = mapped_column(String(32))
    # "active", "past_due" or "canceled".
    status: Mapped[str] = mapped_column(String(12))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    # A lower plan that starts when the paid period ends (a downgrade the customer has asked for).
    pending_plan_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_id"),
    )


class BillingEventRow(Base):
    """Which provider events have been handled, so a repeated delivery changes nothing. No payload is kept."""

    __tablename__ = "billing_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    provider_event_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(48))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_billing_events_provider_event"),
    )
