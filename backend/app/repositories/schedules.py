"""Scan schedules. Every query is limited to one organization, except the scheduler's own claim."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, select, update

from app.database.session import make_session_factory
from app.models.scan import ScanRow
from app.models.schedule import ScanScheduleRow
from app.models.target import TargetRow
from app.schemas.scan import ScanStatus
from app.schemas.schedule import ScheduleOut

INTERVALS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class DueSchedule:
    id: str
    organization_id: str
    target_id: str
    hostname: str
    url: str
    frequency: str
    notify: bool
    created_by: str | None


class ScheduleRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def list_for_organization(self, organization_id: str) -> list[ScheduleOut]:
        """Every verified site of the workspace, with its schedule if it has one."""
        with self._session() as session:
            rows = session.execute(
                select(TargetRow, ScanScheduleRow)
                .outerjoin(ScanScheduleRow, ScanScheduleRow.target_id == TargetRow.id)
                .where(TargetRow.organization_id == organization_id, TargetRow.verified_at.is_not(None))
                .order_by(TargetRow.hostname)
            ).all()
            return [
                ScheduleOut(
                    target_id=t.id,
                    hostname=t.hostname,
                    frequency=s.frequency if s else "off",
                    url=s.url if s else f"https://{t.hostname}/",
                    notify=s.notify if s else True,
                    next_run_at=_aware(s.next_run_at) if s else None,
                    last_run_at=_aware(s.last_run_at) if s else None,
                    last_scan_id=s.last_scan_id if s else None,
                    last_outcome=s.last_outcome if s else None,
                )
                for t, s in rows
            ]

    def set_schedule(
        self,
        organization_id: str,
        target_id: str,
        frequency: str,
        notify: bool,
        url: str,
        user_id: str,
    ) -> bool:
        """False when the site is not in this workspace. frequency "off" removes the schedule."""
        now = _now()
        with self._session.begin() as session:
            target = session.scalar(
                select(TargetRow).where(TargetRow.id == target_id, TargetRow.organization_id == organization_id)
            )
            if target is None:
                return False
            existing = session.scalar(select(ScanScheduleRow).where(ScanScheduleRow.target_id == target_id))
            if frequency == "off":
                if existing is not None:
                    session.execute(delete(ScanScheduleRow).where(ScanScheduleRow.id == existing.id))
                return True
            if existing is None:
                session.add(
                    ScanScheduleRow(
                        id=uuid.uuid4().hex,
                        organization_id=organization_id,
                        target_id=target_id,
                        url=url,
                        frequency=frequency,
                        notify=notify,
                        next_run_at=now,  # the first scan runs at the next scheduler tick
                        created_by=user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                if existing.frequency != frequency:
                    existing.next_run_at = min(_aware(existing.next_run_at) or now, now + INTERVALS[frequency])
                existing.frequency = frequency
                existing.notify = notify
                existing.url = url
                existing.updated_at = now
            return True

    def claim_due(self, now: datetime, limit: int) -> list[DueSchedule]:
        """Takes the schedules that are due and moves each one's next run forward in the same step.

        The update is conditional on the next-run time we read, so two overlapping calls can never both
        claim one schedule: the second finds the time already moved and skips it."""
        claimed: list[DueSchedule] = []
        with self._session.begin() as session:
            rows = session.execute(
                select(ScanScheduleRow, TargetRow.hostname)
                .join(TargetRow, TargetRow.id == ScanScheduleRow.target_id)
                .where(ScanScheduleRow.next_run_at <= now)
                .order_by(ScanScheduleRow.next_run_at)
                .limit(limit)
            ).all()
            for row, hostname in rows:
                interval = INTERVALS.get(row.frequency)
                if interval is None:
                    continue
                result = session.execute(
                    update(ScanScheduleRow)
                    .where(ScanScheduleRow.id == row.id, ScanScheduleRow.next_run_at == row.next_run_at)
                    .values(next_run_at=now + interval, last_run_at=now, last_outcome="started")
                )
                if result.rowcount == 1:  # type: ignore[attr-defined]
                    claimed.append(
                        DueSchedule(
                            row.id,
                            row.organization_id,
                            row.target_id,
                            hostname,
                            row.url,
                            row.frequency,
                            row.notify,
                            row.created_by,
                        )
                    )
        return claimed

    def record_outcome(self, schedule_id: str, outcome: str, scan_id: str | None = None) -> None:
        with self._session.begin() as session:
            values: dict[str, object] = {"last_outcome": outcome[:120]}
            if scan_id is not None:
                values["last_scan_id"] = scan_id
            session.execute(update(ScanScheduleRow).where(ScanScheduleRow.id == schedule_id).values(**values))

    def disable(self, schedule_id: str) -> None:
        with self._session.begin() as session:
            session.execute(delete(ScanScheduleRow).where(ScanScheduleRow.id == schedule_id))

    def previous_completed_scan_id(self, organization_id: str, host: str, before_scan_id: str) -> str | None:
        """The most recent completed scan of this site that came before the given scan."""
        with self._session() as session:
            current = session.get(ScanRow, before_scan_id)
            if current is None:
                return None
            return session.scalar(
                select(ScanRow.id)
                .where(
                    ScanRow.organization_id == organization_id,
                    ScanRow.host == host,
                    ScanRow.status == ScanStatus.COMPLETED.value,
                    ScanRow.created_at < current.created_at,
                    ScanRow.id != before_scan_id,
                )
                .order_by(ScanRow.created_at.desc())
                .limit(1)
            )
