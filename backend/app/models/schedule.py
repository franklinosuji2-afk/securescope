"""Scheduled scans: one optional schedule per verified site."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ScanScheduleRow(Base):
    __tablename__ = "scan_schedules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    target_id: Mapped[str] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    # The address that is scanned. Its host must be the target's host; it is checked again on every run.
    url: Mapped[str] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(8))  # "daily" or "weekly"
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scan_id: Mapped[str | None] = mapped_column(String(32))
    last_outcome: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("target_id", name="uq_scan_schedules_target_id"),
        Index("ix_scan_schedules_organization_id", "organization_id"),
        Index("ix_scan_schedules_next_run_at", "next_run_at"),
    )
