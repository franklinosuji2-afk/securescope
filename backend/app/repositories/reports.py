"""Storage for generated PDF reports. Every read is scoped to an organization."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from app.database.session import make_session_factory
from app.models.scan import ReportRow

# No 0/O/1/I/L, so an ID read out loud or copied from paper is not misread.
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def new_report_id() -> str:
    return "SSR-" + "".join(secrets.choice(_ALPHABET) for _ in range(10))


@dataclass(frozen=True)
class ReportMeta:
    id: str
    scan_id: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ReportIntegrityError(Exception):
    """The stored file no longer matches the checksum recorded when it was made."""


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _meta(row: ReportRow) -> ReportMeta:
    return ReportMeta(row.id, row.scan_id, row.size_bytes, row.sha256, _aware(row.created_at))


class ReportRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def get_meta(self, scan_id: str, organization_id: str) -> ReportMeta | None:
        with self._session() as session:
            row = session.execute(
                select(ReportRow).where(ReportRow.scan_id == scan_id, ReportRow.organization_id == organization_id)
            ).scalar_one_or_none()
            return _meta(row) if row else None

    def save(
        self, report_id: str, scan_id: str, organization_id: str, user_id: str, content: bytes
    ) -> ReportMeta:
        """Stores the file. If another request stored one for this scan first, that one wins."""
        try:
            with self._session.begin() as session:
                row = ReportRow(
                    id=report_id,
                    scan_id=scan_id,
                    organization_id=organization_id,
                    generated_by=user_id,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    content=content,
                    created_at=datetime.now(UTC),
                )
                session.add(row)
                session.flush()
                return _meta(row)
        except IntegrityError:
            existing = self.get_meta(scan_id, organization_id)
            if existing is None:
                raise
            return existing

    def get_file(self, report_id: str, organization_id: str) -> tuple[ReportMeta, bytes] | None:
        with self._session() as session:
            row = session.execute(
                select(ReportRow).where(ReportRow.id == report_id, ReportRow.organization_id == organization_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            content = bytes(row.content)
            if hashlib.sha256(content).hexdigest() != row.sha256:
                raise ReportIntegrityError(report_id)
            return _meta(row), content
