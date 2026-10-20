"""Cookieless website analytics: one row per page view of a public page. No address, no browser string."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PageViewRow(Base):
    __tablename__ = "page_views"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    page: Mapped[str] = mapped_column(String(32))
    referrer_host: Mapped[str | None] = mapped_column(String(255))
    device: Mapped[str] = mapped_column(String(8))
    # One-way daily hash; it changes every UTC day, so it cannot follow a person from one day to the next.
    visitor: Mapped[str] = mapped_column(String(32))

    __table_args__ = (Index("ix_page_views_occurred_at", "occurred_at"),)
