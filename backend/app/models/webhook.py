"""Webhook endpoints: where a workspace wants its scan alerts delivered."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class WebhookEndpointRow(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    # The full address. It can contain a token in its path, so it is never shown again in full.
    url: Mapped[str] = mapped_column(Text)
    # The signing secret is derived from the server key, this id and this version. Rotating adds one.
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    # "webhook" (a signed JSON message) or "slack" (a Slack incoming-webhook message).
    kind: Mapped[str] = mapped_column(String(8), default="webhook", server_default="webhook")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_webhook_endpoints_organization_id", "organization_id"),)


class WebhookDeliveryRow(Base):
    """One delivery to an endpoint: when, which event, and the outcome. No message body, no address, no secret.

    Only the most recent entries per endpoint are kept."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"))
    delivery_id: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(32))
    ok: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(120))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_webhook_deliveries_webhook_id_created_at", "webhook_id", "created_at"),)


class WebhookRetryRow(Base):
    """An alert that could not be delivered and will be tried again later.

    It holds the alert's facts (host, score, titles of new findings: nothing that is not already in the
    signed message) until it is delivered, runs out of attempts or is a day old. Never evidence or secrets."""

    __tablename__ = "webhook_retries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"))
    delivery_id: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text)
    # How many retries have been made so far (the first delivery is not counted).
    retries: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_webhook_retries_next_attempt_at", "next_attempt_at"),
        Index("ix_webhook_retries_webhook_id", "webhook_id"),
    )
