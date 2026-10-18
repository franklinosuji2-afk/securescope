"""Scan repository (SQLAlchemy). All persistence for scans and findings lives here."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from app.database.session import make_session_factory
from app.models.scan import FindingRow, FindingStateRow, ScanRow
from app.scanner.fingerprint import fingerprint
from app.scanner.scoring import count_by_severity
from app.schemas.scan import (
    Confidence,
    Finding,
    FindingStatus,
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
            scan_row = session.get(ScanRow, scan_id)
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
            host = scan_row.host if scan_row else metadata.host
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
                    confidence=f.confidence.value,
                    fingerprint=fingerprint(host, f.id),
                )
                for position, f in enumerate(findings)
            )
            if scan_row is not None and scan_row.organization_id is not None:
                # A scan that stopped at a redirect to another site did not look at this host's own
                # response, so it cannot show that anything was fixed.
                self._record_states(
                    session,
                    scan_row.organization_id,
                    host,
                    findings,
                    may_resolve=metadata.off_origin_redirect is None,
                )

    @staticmethod
    def _record_states(
        session: Session, organization_id: str, host: str, findings: list[Finding], *, may_resolve: bool
    ) -> None:
        """Updates what is known about each finding on this host after a completed scan."""
        now = _now()
        seen = {fingerprint(host, f.id): f for f in findings}
        existing = {
            row.fingerprint: row
            for row in session.scalars(
                select(FindingStateRow).where(
                    FindingStateRow.organization_id == organization_id, FindingStateRow.host == host
                )
            )
        }
        for fp, finding in seen.items():
            row = existing.get(fp)
            if row is None:
                session.add(
                    FindingStateRow(
                        organization_id=organization_id,
                        host=host,
                        fingerprint=fp,
                        finding_id=finding.id,
                        status=FindingStatus.OPEN.value,
                        first_seen_at=now,
                        last_seen_at=now,
                        updated_at=now,
                    )
                )
                continue
            row.last_seen_at = now
            if row.status == FindingStatus.RESOLVED.value:  # it came back
                row.status = FindingStatus.OPEN.value
                row.resolved_at = None
                row.updated_at = now
        if may_resolve:
            for fp, row in existing.items():
                if fp not in seen and row.status == FindingStatus.OPEN.value:
                    row.status = FindingStatus.RESOLVED.value
                    row.resolved_at = now
                    row.updated_at = now

    def set_finding_status(
        self,
        organization_id: str,
        fingerprint_value: str,
        status: FindingStatus,
        note: str | None,
        user_id: str,
    ) -> bool:
        """Analyst triage. Returns False when this organization has no such finding."""
        with self._session.begin() as session:
            row = session.scalar(
                select(FindingStateRow).where(
                    FindingStateRow.organization_id == organization_id,
                    FindingStateRow.fingerprint == fingerprint_value,
                )
            )
            if row is None:
                return False
            row.status = status.value
            row.note = note
            row.updated_by = user_id
            row.updated_at = _now()
            row.resolved_at = None
            return True

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
    def _findings(row: ScanRow, states: dict[str, FindingStateRow] | None = None) -> list[Finding]:
        out = []
        for f in row.findings:
            state = (states or {}).get(f.fingerprint or "")
            out.append(
                Finding(
                    id=f.finding_id,
                    title=f.title,
                    severity=Severity(f.severity),
                    category=f.category,
                    description=f.description,
                    evidence=f.evidence,
                    remediation=f.remediation,
                    confidence=Confidence(f.confidence),
                    fingerprint=f.fingerprint,
                    status=FindingStatus(state.status) if state else FindingStatus.OPEN,
                    status_note=state.note if state else None,
                    first_seen_at=_aware(state.first_seen_at) if state else None,
                    last_seen_at=_aware(state.last_seen_at) if state else None,
                )
            )
        return out

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
            states = {
                state.fingerprint: state
                for state in session.scalars(
                    select(FindingStateRow).where(
                        FindingStateRow.organization_id == organization_id,
                        FindingStateRow.host == row.host,
                    )
                )
            }
            findings = self._findings(row, states)
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
