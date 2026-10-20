"""Target repository. Every method takes the organization id; there is no unscoped read."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.exc import IntegrityError

from app.database.session import make_session_factory
from app.models.target import TargetRow
from app.schemas.target import TargetOut
from app.security.ownership import challenge_value, dns_record_name, http_file_url

CHALLENGE_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class DuplicateTargetError(Exception):
    pass


def verification_expiry(row: TargetRow, valid_days: int) -> datetime | None:
    """When a proven domain stops being authorised, or None if it is unproven or never expires."""
    verified = _aware(row.verified_at)
    if verified is None or valid_days <= 0:
        return None
    return verified + timedelta(days=valid_days)


def to_out(row: TargetRow, valid_days: int = 0) -> TargetOut:
    expires = _aware(row.challenge_expires_at)
    if expires is None:
        raise ValueError("target row without challenge expiry")
    lapses = verification_expiry(row, valid_days)
    if row.verified_at:
        status = "reverify" if lapses is not None and lapses <= _now() else "verified"
    else:
        status = "expired" if expires <= _now() else "pending"
    return TargetOut(
        id=row.id,
        hostname=row.hostname,
        status=status,
        verification_expires_at=lapses,
        challenge_token=row.challenge_token,
        challenge_expires_at=expires,
        verified_at=_aware(row.verified_at),
        verification_method=row.verification_method,
        last_check_at=_aware(row.last_check_at),
        last_check_error=row.last_check_error,
        created_at=_aware(row.created_at),
        dns_record_name=dns_record_name(row.hostname),
        dns_record_value=challenge_value(row.challenge_token),
        http_file_url=http_file_url(row.hostname),
        http_file_content=challenge_value(row.challenge_token),
    )


class TargetRepository:
    def __init__(self, engine: Engine, verification_valid_days: int = 0) -> None:
        self._session = make_session_factory(engine)
        self._valid_days = verification_valid_days

    def create(self, organization_id: str, hostname: str, created_by: str) -> TargetOut:
        now = _now()
        row = TargetRow(
            id=uuid.uuid4().hex,
            organization_id=organization_id,
            hostname=hostname,
            challenge_token=secrets.token_hex(16),
            challenge_expires_at=now + CHALLENGE_TTL,
            created_by=created_by,
            created_at=now,
        )
        try:
            with self._session.begin() as session:
                session.add(row)
                session.flush()
                return to_out(row, self._valid_days)
        except IntegrityError as exc:
            raise DuplicateTargetError from exc

    def get(self, target_id: str, organization_id: str) -> TargetOut | None:
        with self._session() as session:
            row = session.get(TargetRow, target_id)
            if row is None or row.organization_id != organization_id:
                return None
            return to_out(row, self._valid_days)

    def list(self, organization_id: str) -> list[TargetOut]:
        with self._session() as session:
            rows = session.scalars(
                select(TargetRow)
                .where(TargetRow.organization_id == organization_id)
                .order_by(TargetRow.hostname)
            ).all()
            return [to_out(r) for r in rows]

    def find_verified(self, organization_id: str, hostname: str) -> TargetOut | None:
        with self._session() as session:
            row = session.scalar(
                select(TargetRow).where(
                    TargetRow.organization_id == organization_id,
                    TargetRow.hostname == hostname,
                    TargetRow.verified_at.is_not(None),
                )
            )
            if row is None:
                return None
            out = to_out(row, self._valid_days)
            return out if out.status == "verified" else None

    def find_by_host(self, organization_id: str, hostname: str) -> TargetOut | None:
        """The target for a host in any state, so callers can explain why a scan is refused."""
        with self._session() as session:
            row = session.scalar(
                select(TargetRow).where(
                    TargetRow.organization_id == organization_id, TargetRow.hostname == hostname
                )
            )
            return to_out(row, self._valid_days) if row else None

    def delete(self, target_id: str, organization_id: str) -> bool:
        with self._session.begin() as session:
            result = session.execute(
                delete(TargetRow).where(
                    TargetRow.id == target_id, TargetRow.organization_id == organization_id
                )
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def regenerate_challenge(self, target_id: str, organization_id: str) -> TargetOut | None:
        """New token and a fresh expiry. A verified target keeps its verification."""
        with self._session.begin() as session:
            row = session.get(TargetRow, target_id)
            if row is None or row.organization_id != organization_id:
                return None
            row.challenge_token = secrets.token_hex(16)
            row.challenge_expires_at = _now() + CHALLENGE_TTL
            if row.verified_at is None:
                row.last_check_error = None
            session.flush()
            return to_out(row, self._valid_days)

    def record_check(
        self,
        target_id: str,
        organization_id: str,
        *,
        method: str,
        error: str | None,
    ) -> TargetOut | None:
        now = _now()
        values: dict[str, object] = {"last_check_at": now, "last_check_error": error}
        if error is None:
            values.update(verified_at=now, verification_method=method)
        with self._session.begin() as session:
            session.execute(
                update(TargetRow)
                .where(TargetRow.id == target_id, TargetRow.organization_id == organization_id)
                .values(**values)
            )
            row = session.get(TargetRow, target_id)
            return to_out(row, self._valid_days) if row and row.organization_id == organization_id else None
