"""ORM models. Schema changes go through Alembic migrations, never `create_all`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class ScanRow(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Nullable only for rows created before accounts existed (v0.1); those are invisible to everyone.
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # The verified target that authorised this scan (NULL for scans created before targets existed).
    target_id: Mapped[str | None] = mapped_column(ForeignKey("targets.id", ondelete="SET NULL"))
    target_url: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(2))
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    authorization_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    findings: Mapped[list[FindingRow]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", order_by="FindingRow.position"
    )

    __table_args__ = (
        Index("ix_scans_created_at", "created_at"),
        Index("ix_scans_organization_id_created_at", "organization_id", "created_at"),
    )


class FindingRow(Base):
    __tablename__ = "findings"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    finding_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)

    scan: Mapped[ScanRow] = relationship(back_populates="findings")

    __table_args__ = (Index("ix_findings_scan_id_position", "scan_id", "position"),)
