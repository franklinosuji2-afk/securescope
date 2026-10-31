"""Plan assignment and usage counting. Every method takes the organization id."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.billing.lifecycle import effective_plan_id
from app.billing.plans import INTERNAL, get_plan
from app.database.session import make_session_factory
from app.models.account import MemberRow, OrganizationRow, UserRow
from app.models.billing import OrganizationPlanRow, SubscriptionRow
from app.models.scan import ScanRow
from app.models.target import TargetRow
from app.repositories.billing import state_from_row
from app.schemas.scan import ScanStatus


def _now() -> datetime:
    return datetime.now(UTC)


def organizations_by_plan(session: Session, now: datetime) -> dict[str, list[str]]:
    """The organizations that have a stored plan or a subscription, grouped by the id of the plan that applies at
    `now`: a paid subscription gives its plan while the paid period lasts, the stored base plan applies otherwise,
    and an unknown plan id falls back to the default. Organizations not in the result follow the default plan.
    Used by the retention clean-ups, so website and App Scanning history follow the same plan."""
    base = {
        org: plan
        for org, plan in session.execute(
            select(OrganizationPlanRow.organization_id, OrganizationPlanRow.plan_id)
        )
    }
    subs = {row.organization_id: state_from_row(row) for row in session.scalars(select(SubscriptionRow))}
    by_plan: dict[str, list[str]] = {}
    for org in base.keys() | subs.keys():
        plan_id = get_plan(effective_plan_id(base.get(org), subs.get(org), now)).id
        by_plan.setdefault(plan_id, []).append(org)
    return by_plan


def lock_organization(session: Session, organization_id: str) -> None:
    """Serialises quota checks for one organization: later requests wait here until this transaction ends, so
    two requests at the same moment cannot both pass the same count. (SQLite has one writer at a time anyway.)"""
    session.execute(select(OrganizationRow.id).where(OrganizationRow.id == organization_id).with_for_update())


class PlanRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def plan_id(self, organization_id: str) -> str | None:
        with self._session() as session:
            return session.scalar(
                select(OrganizationPlanRow.plan_id).where(
                    OrganizationPlanRow.organization_id == organization_id
                )
            )

    def set_plan(self, organization_id: str, plan_id: str, source: str) -> None:
        now = _now()
        with self._session.begin() as session:
            row = session.get(OrganizationPlanRow, organization_id)
            if row is None:
                session.add(
                    OrganizationPlanRow(
                        organization_id=organization_id,
                        plan_id=plan_id,
                        source=source,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.plan_id = plan_id
                row.source = source
                row.updated_at = now

    def usage(self, organization_id: str, period_start: datetime) -> tuple[int, int]:
        """(websites registered, scans started since `period_start`). Scans that failed are not counted."""
        with self._session() as session:
            websites = session.scalar(
                select(func.count())
                .select_from(TargetRow)
                .where(TargetRow.organization_id == organization_id)
            )
            scans = session.scalar(
                select(func.count())
                .select_from(ScanRow)
                .where(
                    ScanRow.organization_id == organization_id,
                    ScanRow.created_at >= period_start,
                    ScanRow.status != ScanStatus.FAILED.value,
                )
            )
        return int(websites or 0), int(scans or 0)

    def assign_internal_to_operator(self, admin_email: str) -> int:
        """Puts the workspaces the operator owns on the internal plan, unless they already have a plan row."""
        address = admin_email.strip().lower()
        if not address:
            return 0
        assigned = 0
        with self._session.begin() as session:
            org_ids = session.scalars(
                select(MemberRow.organization_id)
                .join(UserRow, UserRow.id == MemberRow.user_id)
                .join(OrganizationRow, OrganizationRow.id == MemberRow.organization_id)
                .where(func.lower(UserRow.email) == address, MemberRow.role == "OWNER")
            ).all()
            now = _now()
            for org_id in org_ids:
                if session.get(OrganizationPlanRow, org_id) is None:
                    session.add(
                        OrganizationPlanRow(
                            organization_id=org_id,
                            plan_id=INTERNAL.id,
                            source="system",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    assigned += 1
        return assigned
