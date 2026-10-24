"""Private customer feedback. One entry per person; every query for a person's own entry is keyed by user id."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database.session import make_session_factory
from app.models.account import MemberRow
from app.models.feedback import FeedbackRow


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class FeedbackRecord:
    rating: int
    category: str | None
    message: str | None
    created_at: datetime
    updated_at: datetime


def _record(row: FeedbackRow) -> FeedbackRecord:
    return FeedbackRecord(
        row.rating, row.category, row.message, _aware(row.created_at), _aware(row.updated_at)
    )


@dataclass(frozen=True)
class FeedbackSummary:
    count: int
    average: float | None
    by_rating: dict[int, int]
    latest: list[FeedbackRecord]


class FeedbackRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def get(self, user_id: str) -> FeedbackRecord | None:
        with self._session() as session:
            row = session.scalar(select(FeedbackRow).where(FeedbackRow.user_id == user_id))
            return _record(row) if row else None

    def save(self, user_id: str, rating: int, category: str | None, message: str | None) -> FeedbackRecord:
        """Creates the person's entry or replaces it. A second call never makes a second row."""
        for attempt in range(2):
            now = _now()
            try:
                with self._session.begin() as session:
                    row = session.scalar(select(FeedbackRow).where(FeedbackRow.user_id == user_id))
                    if row is None:
                        row = FeedbackRow(
                            id=uuid.uuid4().hex,
                            user_id=user_id,
                            rating=rating,
                            category=category,
                            message=message,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(row)
                    else:
                        row.rating = rating
                        row.category = category
                        row.message = message
                        row.updated_at = now
                    session.flush()
                    return _record(row)
            except IntegrityError:
                # Two first submissions at the same moment: the second one retries as an update.
                if attempt == 1:
                    raise
        raise RuntimeError("unreachable")

    def delete(self, user_id: str) -> bool:
        with self._session.begin() as session:
            result = session.execute(delete(FeedbackRow).where(FeedbackRow.user_id == user_id))
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def entries(self, limit: int = 500) -> list[tuple[FeedbackRecord, str | None]]:
        """For the operator: the newest entries, each with the id of a workspace its author owns (or None for
        someone who only belongs to other people's workspaces). The author's identity is not returned."""
        owned = (
            select(MemberRow.user_id, func.min(MemberRow.organization_id).label("organization_id"))
            .where(MemberRow.role == "OWNER")
            .group_by(MemberRow.user_id)
            .subquery()
        )
        with self._session() as session:
            rows = session.execute(
                select(FeedbackRow, owned.c.organization_id)
                .outerjoin(owned, owned.c.user_id == FeedbackRow.user_id)
                .order_by(FeedbackRow.updated_at.desc())
                .limit(limit)
            ).all()
            return [(_record(row), org) for row, org in rows]

    def summary(self, limit: int = 20) -> FeedbackSummary:
        """For the operator: totals and the latest entries. Entries carry no name or email address."""
        with self._session() as session:
            count = int(session.scalar(select(func.count()).select_from(FeedbackRow)) or 0)
            average = session.scalar(select(func.avg(FeedbackRow.rating)))
            by_rating = {
                int(r): int(c)
                for r, c in session.execute(
                    select(FeedbackRow.rating, func.count()).group_by(FeedbackRow.rating)
                )
            }
            rows = session.scalars(
                select(FeedbackRow).order_by(FeedbackRow.updated_at.desc()).limit(limit)
            ).all()
            return FeedbackSummary(
                count,
                round(float(average), 2) if average is not None else None,
                {star: by_rating.get(star, 0) for star in range(1, 6)},
                [_record(r) for r in rows],
            )
