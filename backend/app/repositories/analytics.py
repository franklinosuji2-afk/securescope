"""Storage for the cookieless website analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select

from app.database.session import make_session_factory
from app.models.analytics import PageViewRow
from app.services.analytics import View


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class AnalyticsRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def add(self, view: View) -> None:
        with self._session.begin() as session:
            session.add(
                PageViewRow(
                    occurred_at=view.occurred_at,
                    page=view.page,
                    referrer_host=view.referrer_host,
                    device=view.device,
                    visitor=view.visitor,
                )
            )

    def views_since(self, since: datetime, limit: int = 200_000) -> list[View]:
        with self._session() as session:
            rows = session.scalars(
                select(PageViewRow)
                .where(PageViewRow.occurred_at >= since)
                .order_by(PageViewRow.occurred_at)
                .limit(limit)
            )
            return [View(_aware(r.occurred_at), r.page, r.referrer_host, r.device, r.visitor) for r in rows]

    def last_view_at(self) -> datetime | None:
        with self._session() as session:
            value = session.scalar(select(func.max(PageViewRow.occurred_at)))
            return _aware(value) if value else None

    def delete_older_than(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self._session.begin() as session:
            result = session.execute(delete(PageViewRow).where(PageViewRow.occurred_at < cutoff))
            return int(getattr(result, "rowcount", 0) or 0)
