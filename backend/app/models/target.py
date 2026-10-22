"""Targets: domains an organization has declared and (optionally) proven it controls."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class TargetRow(Base):
    __tablename__ = "targets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    hostname: Mapped[str] = mapped_column(String(253))
    # The challenge value is public by design (it is published in DNS or on the website).
    challenge_token: Mapped[str] = mapped_column(String(64))
    challenge_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_method: Mapped[str | None] = mapped_column(String(16))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Which of the workspace's clients this site belongs to (agency workspaces only).
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "hostname", name="uq_targets_organization_id_hostname"),
        Index("ix_targets_organization_id", "organization_id"),
    )
