"""Activation funnel for the operator, counted from rows that already exist.

Nothing here is tracked separately and nothing identifies a person: the result is a handful of counts and one
median per cohort, never an id, an address or a site name. The cohort is the workspaces created in the period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from sqlalchemy import Engine, func, select

from app.database.session import make_session_factory
from app.models.account import AuditEventRow, OrganizationRow
from app.models.integration import ApiTokenRow
from app.models.scan import ScanRow
from app.models.schedule import ScanScheduleRow
from app.models.target import TargetRow
from app.schemas.scan import ScanStatus

# Counts below this are shown but flagged in the interface: one person is not a trend.
SMALL_COHORT = 5


@dataclass(frozen=True)
class Activation:
    created: int
    website_added: int
    website_verified: int
    first_scan_completed: int
    second_scan_completed: int
    monitoring_enabled: int
    report_downloaded: int
    api_token_created: int
    median_seconds_to_first_scan: int | None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ActivationRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def funnel(self, since: datetime) -> Activation:
        with self._session() as session:
            cohort = select(OrganizationRow.id).where(OrganizationRow.created_at >= since)
            created = int(session.scalar(select(func.count()).select_from(cohort.subquery())) or 0)
            added = int(
                session.scalar(
                    select(func.count(func.distinct(TargetRow.organization_id))).where(
                        TargetRow.organization_id.in_(cohort)
                    )
                )
                or 0
            )
            verified = int(
                session.scalar(
                    select(func.count(func.distinct(TargetRow.organization_id))).where(
                        TargetRow.organization_id.in_(cohort), TargetRow.verified_at.is_not(None)
                    )
                )
                or 0
            )
            per_org = session.execute(
                select(
                    ScanRow.organization_id,
                    func.count(),
                    func.min(ScanRow.finished_at),
                    OrganizationRow.created_at,
                )
                .join(OrganizationRow, OrganizationRow.id == ScanRow.organization_id)
                .where(
                    ScanRow.organization_id.in_(cohort),
                    ScanRow.status == ScanStatus.COMPLETED.value,
                    ScanRow.finished_at.is_not(None),
                )
                .group_by(ScanRow.organization_id, OrganizationRow.created_at)
            ).all()
            durations = [
                max(0, int((_aware(first) - _aware(made)).total_seconds()))
                for _org, _count, first, made in per_org
                if first is not None
            ]
            scheduled = int(
                session.scalar(
                    select(func.count(func.distinct(ScanScheduleRow.organization_id))).where(
                        ScanScheduleRow.organization_id.in_(cohort)
                    )
                )
                or 0
            )
            downloaded = int(
                session.scalar(
                    select(func.count(func.distinct(AuditEventRow.organization_id))).where(
                        AuditEventRow.organization_id.in_(cohort),
                        AuditEventRow.event_type == "report.downloaded",
                    )
                )
                or 0
            )
            tokens = int(
                session.scalar(
                    select(func.count(func.distinct(ApiTokenRow.organization_id))).where(
                        ApiTokenRow.organization_id.in_(cohort)
                    )
                )
                or 0
            )
        return Activation(
            created=created,
            website_added=added,
            website_verified=verified,
            first_scan_completed=len(per_org),
            second_scan_completed=sum(1 for _o, count, _f, _m in per_org if count >= 2),
            monitoring_enabled=scheduled,
            report_downloaded=downloaded,
            api_token_created=tokens,
            median_seconds_to_first_scan=int(median(durations)) if durations else None,
        )
