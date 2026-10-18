"""Scan repository (SQLAlchemy). All persistence for scans and findings lives here."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, update

from app.database.session import make_session_factory
from app.models.scan import FindingRow, ScanRow
from app.scanner.scoring import count_by_severity
from app.schemas.scan import (
    Finding,
    ScanDetail,
    ScanStatus,
    ScanSummary,
    Severity,
    TargetMetadata,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ScanRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session = make_session_factory(engine)

    # --- writes -----------------------------------------------------------------------

    def create_scan(
        self,
        organization_id: str,
        requested_by: str,
        target_url: str,
        host: str,
        target_id: str | None = None,
    ) -> str:
        scan_id = uuid.uuid4().hex
        now = _now()
        with self._session.begin() as session:
            session.add(
                ScanRow(
                    id=scan_id,
                    organization_id=organization_id,
                    requested_by=requested_by,
                    target_id=target_id,
                    target_url=target_url,
                    host=host,
                    status=ScanStatus.QUEUED.value,
                    authorization_confirmed_at=now,
                    created_at=now,
                )
            )
        return scan_id

    def mark_running(self, scan_id: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(ScanRow)
                .where(ScanRow.id == scan_id)
                .values(status=ScanStatus.RUNNING.value, started_at=_now())
            )

    def complete_scan(
        self,
        scan_id: str,
        findings: list[Finding],
        score: int,
        grade: str,
        metadata: TargetMetadata,
    ) -> None:
        with self._session.begin() as session:
            session.execute(
                update(ScanRow)
                .where(ScanRow.id == scan_id)
                .values(
                    status=ScanStatus.COMPLETED.value,
                    score=score,
                    grade=grade,
                    metadata_json=metadata.model_dump_json(),
                    finished_at=_now(),
                )
            )
            session.add_all(
                FindingRow(
                    scan_id=scan_id,
                    position=position,
                    finding_id=f.id,
                    title=f.title,
                    severity=f.severity.value,
                    category=f.category,
                    description=f.description,
                    evidence=f.evidence,
                    remediation=f.remediation,
                )
                for position, f in enumerate(findings)
            )

    def fail_scan(self, scan_id: str, error: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(ScanRow)
                .where(ScanRow.id == scan_id)
                .values(status=ScanStatus.FAILED.value, error=error, finished_at=_now())
            )

    def delete_older_than(self, days: int) -> int:
        cutoff = _now() - timedelta(days=days)
        with self._session.begin() as session:
            # Delete findings explicitly so behaviour does not depend on the DB enforcing FKs.
            old_ids = select(ScanRow.id).where(ScanRow.created_at < cutoff)
            session.execute(delete(FindingRow).where(FindingRow.scan_id.in_(old_ids)))
            result = session.execute(delete(ScanRow).where(ScanRow.created_at < cutoff))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def fail_interrupted(self) -> int:
        """Scans left queued/running by a previous process can never finish; mark them failed."""
        with self._session.begin() as session:
            result = session.execute(
                update(ScanRow)
                .where(ScanRow.status.in_([ScanStatus.QUEUED.value, ScanStatus.RUNNING.value]))
                .values(
                    status=ScanStatus.FAILED.value,
                    error="The service restarted before this scan finished.",
                    finished_at=_now(),
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # --- reads ------------------------------------------------------------------------

    @staticmethod
    def _findings(row: ScanRow) -> list[Finding]:
        return [
            Finding(
                id=f.finding_id,
                title=f.title,
                severity=Severity(f.severity),
                category=f.category,
                description=f.description,
                evidence=f.evidence,
                remediation=f.remediation,
            )
            for f in row.findings
        ]

    @staticmethod
    def _summary(row: ScanRow, findings: list[Finding]) -> dict[str, object]:
        return {
            "id": row.id,
            "target_url": row.target_url,
            "host": row.host,
            "status": ScanStatus(row.status),
            "score": row.score,
            "grade": row.grade,
            "created_at": _aware(row.created_at),
            "finished_at": _aware(row.finished_at),
            "counts": count_by_severity(findings) if row.status == "completed" else {},
        }

    def get_scan(self, scan_id: str, organization_id: str) -> ScanDetail | None:
        """Returns the scan only if it belongs to `organization_id` (tenant isolation)."""
        with self._session() as session:
            row = session.get(ScanRow, scan_id)
            if row is None or row.organization_id != organization_id:
                return None
            findings = self._findings(row)
            metadata = TargetMetadata(**json.loads(row.metadata_json)) if row.metadata_json else None
            return ScanDetail(
                **self._summary(row, findings),
                error=row.error,
                metadata=metadata,
                findings=findings,
            )

    def list_scans(
        self, organization_id: str, limit: int = 25, offset: int = 0
    ) -> tuple[list[ScanSummary], int]:
        with self._session() as session:
            scope = ScanRow.organization_id == organization_id
            total = session.scalar(select(func.count()).select_from(ScanRow).where(scope)) or 0
            rows = session.scalars(
                select(ScanRow)
                .where(scope)
                .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            items = [ScanSummary(**self._summary(r, self._findings(r))) for r in rows]
        return items, total

    def ping(self) -> bool:
        """Cheap connectivity check used by the readiness endpoint."""
        with self.engine.connect() as connection:
            connection.execute(select(1))
        return True
