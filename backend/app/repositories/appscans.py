"""App Scanning persistence: projects and runs. Every method takes the organization id and never looks at
another workspace's rows. Quota checks and inserts share one transaction under the workspace lock, as for
website scans, so simultaneous requests cannot both take the last run."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError

from app.appscan.redaction import redact_text, redact_value
from app.appscan.states import ACTIVE, FINAL, KINDS, NOT_COUNTED, AppScanStatus
from app.billing.errors import PlanLimitError
from app.database.session import make_session_factory
from app.models.app_scan import AppProjectRow, AppScanRow
from app.repositories.plans import lock_organization

MAX_INPUTS = 5
MAX_JSON_CHARS = 8_000
_KEY = re.compile(r"^[\x21-\x7e]{1,80}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
PROJECT_SOURCES = ("upload", "ci")


class AppProjectNameTaken(Exception):
    pass


class AppProjectNotFound(Exception):
    pass


class AppRateLimited(Exception):
    """Too many runs for one project in the last hour. The message is safe to show."""


class IdempotencyKeyReused(Exception):
    """The key was already used for a different project."""


@dataclass(frozen=True, slots=True)
class AcceptedRun:
    scan_id: str
    replay: (
        bool  # True when the key had been used before: the first run is returned and nothing new is charged
    )


@dataclass(frozen=True, slots=True)
class AppUsage:
    runs: int
    projects: int


def _now() -> datetime:
    return datetime.now(UTC)


def clean_project_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not 1 <= len(cleaned) <= 120 or _CONTROL.search(cleaned):
        raise ValueError("A project name must be 1 to 120 characters without control characters.")
    return redact_text(cleaned)


def _json(value: object) -> str:
    text = json.dumps(redact_value(value), separators=(",", ":"), ensure_ascii=True)
    if len(text) > MAX_JSON_CHARS:
        raise ValueError("The details are too large to store.")
    return text


def _clean_kinds(kinds: list[str]) -> list[str]:
    unique = sorted(set(kinds))
    if not unique or any(k not in KINDS for k in unique):
        raise ValueError("Choose at least one supported check.")
    return unique


class AppScanRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    # --- projects -----------------------------------------------------------------------

    def create_project(
        self, organization_id: str, created_by: str | None, name: str, source: str, project_limit: int | None
    ) -> str:
        if source not in PROJECT_SOURCES:
            raise ValueError("Unknown project source.")
        cleaned = clean_project_name(name)
        project_id = uuid.uuid4().hex
        try:
            with self._session.begin() as session:
                lock_organization(session, organization_id)
                if project_limit is not None:
                    used = session.scalar(
                        select(func.count())
                        .select_from(AppProjectRow)
                        .where(
                            AppProjectRow.organization_id == organization_id,
                            AppProjectRow.archived_at.is_(None),
                        )
                    )
                    if int(used or 0) >= project_limit:
                        raise PlanLimitError(
                            f"Your plan includes {project_limit} App Scanning projects and they are all in use. "
                            "Archive one or upgrade."
                        )
                session.add(
                    AppProjectRow(
                        id=project_id,
                        organization_id=organization_id,
                        name=cleaned,
                        source=source,
                        created_by=created_by,
                        created_at=_now(),
                    )
                )
        except IntegrityError as exc:
            raise AppProjectNameTaken(cleaned) from exc
        return project_id

    def list_projects(self, organization_id: str, include_archived: bool = False) -> list[AppProjectRow]:
        with self._session() as session:
            query = select(AppProjectRow).where(AppProjectRow.organization_id == organization_id)
            if not include_archived:
                query = query.where(AppProjectRow.archived_at.is_(None))
            rows = list(session.scalars(query.order_by(AppProjectRow.created_at, AppProjectRow.id)))
            session.expunge_all()
            return rows

    def archive_project(self, organization_id: str, project_id: str) -> bool:
        with self._session.begin() as session:
            result = session.execute(
                update(AppProjectRow)
                .where(
                    AppProjectRow.id == project_id,
                    AppProjectRow.organization_id == organization_id,
                    AppProjectRow.archived_at.is_(None),
                )
                .values(archived_at=_now())
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    # --- runs ---------------------------------------------------------------------------

    def accept_run(
        self,
        organization_id: str,
        project_id: str,
        requested_by: str | None,
        kinds: list[str],
        inputs: list[dict[str, object]],
        monthly_limit: int | None,
        period_start: datetime,
        per_project_hourly_limit: int | None,
        idempotency_key: str | None = None,
        ref: str | None = None,
    ) -> AcceptedRun:
        """Stores one accepted request. Invalid requests raise before anything is written or counted."""
        chosen = _clean_kinds(kinds)
        if len(inputs) > MAX_INPUTS:
            raise ValueError("Too many inputs.")
        inputs_json = _json(inputs)
        kinds_json = _json(chosen)
        safe_ref = redact_text(ref.strip())[:120] if ref and ref.strip() else None
        if idempotency_key is not None and not _KEY.match(idempotency_key):
            raise ValueError("The idempotency key must be 1 to 80 printable characters.")
        scan_id = uuid.uuid4().hex
        now = _now()
        try:
            with self._session.begin() as session:
                lock_organization(session, organization_id)
                project = session.scalar(
                    select(AppProjectRow).where(
                        AppProjectRow.id == project_id,
                        AppProjectRow.organization_id == organization_id,
                        AppProjectRow.archived_at.is_(None),
                    )
                )
                if project is None:
                    raise AppProjectNotFound(project_id)
                if idempotency_key is not None:
                    earlier = session.execute(
                        select(AppScanRow.id, AppScanRow.project_id).where(
                            AppScanRow.organization_id == organization_id,
                            AppScanRow.idempotency_key == idempotency_key,
                        )
                    ).first()
                    if earlier is not None:
                        if earlier[1] != project_id:
                            raise IdempotencyKeyReused(idempotency_key)
                        return AcceptedRun(earlier[0], replay=True)
                if per_project_hourly_limit is not None:
                    recent = session.scalar(
                        select(func.count())
                        .select_from(AppScanRow)
                        .where(
                            AppScanRow.organization_id == organization_id,
                            AppScanRow.project_id == project_id,
                            AppScanRow.created_at >= now - timedelta(hours=1),
                        )
                    )
                    if int(recent or 0) >= per_project_hourly_limit:
                        raise AppRateLimited(
                            "This project has reached its hourly limit for App Scanning runs. Try again later."
                        )
                if monthly_limit is not None:
                    used = self._counted_runs(session, organization_id, period_start)
                    if used >= monthly_limit:
                        raise PlanLimitError(
                            f"Your plan includes {monthly_limit} App Scanning runs per month and they are used up. "
                            "The allowance renews at the start of next month, or you can upgrade."
                        )
                session.add(
                    AppScanRow(
                        id=scan_id,
                        organization_id=organization_id,
                        project_id=project_id,
                        requested_by=requested_by,
                        status=AppScanStatus.QUEUED.value,
                        kinds_json=kinds_json,
                        inputs_json=inputs_json,
                        ref=safe_ref,
                        idempotency_key=idempotency_key,
                        created_at=now,
                    )
                )
        except IntegrityError:
            # Two requests with the same key raced past the check; the unique index let only one in.
            if idempotency_key is None:
                raise
            existing = self.find_by_idempotency_key(organization_id, idempotency_key)
            if existing is None or existing[1] != project_id:
                raise
            return AcceptedRun(existing[0], replay=True)
        return AcceptedRun(scan_id, replay=False)

    def find_by_idempotency_key(self, organization_id: str, key: str) -> tuple[str, str] | None:
        """(run id, project id) for this workspace's run made with `key`."""
        with self._session() as session:
            row = session.execute(
                select(AppScanRow.id, AppScanRow.project_id).where(
                    AppScanRow.organization_id == organization_id, AppScanRow.idempotency_key == key
                )
            ).first()
        return None if row is None else (row[0], row[1])

    def start_run(self, organization_id: str, scan_id: str) -> bool:
        with self._session.begin() as session:
            result = session.execute(
                update(AppScanRow)
                .where(
                    AppScanRow.id == scan_id,
                    AppScanRow.organization_id == organization_id,
                    AppScanRow.status == AppScanStatus.QUEUED.value,
                )
                .values(status=AppScanStatus.RUNNING.value, started_at=_now())
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def finish_run(
        self,
        organization_id: str,
        scan_id: str,
        status: AppScanStatus,
        error: str | None = None,
        checks_run: list[str] | None = None,
        checks_skipped: list[dict[str, str]] | None = None,
        scanners: list[dict[str, str]] | None = None,
    ) -> bool:
        """Moves an active run to a final state. A run that is already final is left as it is (returns False)."""
        if status.value not in FINAL:
            raise ValueError("A run can only be finished with a final state.")
        values: dict[str, object] = {
            "status": status.value,
            "finished_at": _now(),
            "error": redact_text(error)[:500] if error else None,
        }
        if checks_run is not None:
            values["checks_run_json"] = _json(checks_run)
        if checks_skipped is not None:
            values["checks_skipped_json"] = _json(checks_skipped)
        if scanners is not None:
            values["scanners_json"] = _json(scanners)
        with self._session.begin() as session:
            result = session.execute(
                update(AppScanRow)
                .where(
                    AppScanRow.id == scan_id,
                    AppScanRow.organization_id == organization_id,
                    AppScanRow.status.in_(ACTIVE),
                )
                .values(**values)
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def interrupt_unfinished(self) -> int:
        """Runs a stopped process left queued or running can never finish. They are marked interrupted, and an
        interrupted run is not counted against the plan."""
        with self._session.begin() as session:
            result = session.execute(
                update(AppScanRow)
                .where(AppScanRow.status.in_(ACTIVE))
                .values(
                    status=AppScanStatus.INTERRUPTED.value,
                    error="The service restarted before this run finished.",
                    finished_at=_now(),
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def get_run(self, organization_id: str, scan_id: str) -> AppScanRow | None:
        with self._session() as session:
            row = session.scalar(
                select(AppScanRow).where(
                    AppScanRow.id == scan_id, AppScanRow.organization_id == organization_id
                )
            )
            if row is not None:
                session.expunge(row)
            return row

    # --- usage --------------------------------------------------------------------------

    @staticmethod
    def _counted_runs(session, organization_id: str, period_start: datetime) -> int:  # type: ignore[no-untyped-def]
        used = session.scalar(
            select(func.count())
            .select_from(AppScanRow)
            .where(
                AppScanRow.organization_id == organization_id,
                AppScanRow.created_at >= period_start,
                AppScanRow.status.not_in(NOT_COUNTED),
            )
        )
        return int(used or 0)

    def usage(self, organization_id: str, period_start: datetime) -> AppUsage:
        """(runs counted this period, projects in use). Never reads website scan rows."""
        with self._session() as session:
            runs = self._counted_runs(session, organization_id, period_start)
            projects = session.scalar(
                select(func.count())
                .select_from(AppProjectRow)
                .where(AppProjectRow.organization_id == organization_id, AppProjectRow.archived_at.is_(None))
            )
        return AppUsage(runs, int(projects or 0))
