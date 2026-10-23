"""Integrations: API tokens for CI and public score badges."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ApiTokenRow(Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    # The token acts as this person, inside this workspace only, and stops working if they leave it.
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    # Only the SHA-256 digest is stored, never the token. The prefix lets a person recognise it in a list.
    token_hash: Mapped[str] = mapped_column(String(64))
    prefix: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
        Index("ix_api_tokens_organization_id", "organization_id"),
    )


class SiteBadgeRow(Base):
    __tablename__ = "site_badges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    target_id: Mapped[str] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    # Part of the public badge address. It is a link, not a credential: anyone who has it can see the badge,
    # which shows only the latest score and grade of that one site. Turning the badge off deletes the row.
    token: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("target_id", name="uq_site_badges_target_id"),
        UniqueConstraint("token", name="uq_site_badges_token"),
        Index("ix_site_badges_organization_id", "organization_id"),
    )
