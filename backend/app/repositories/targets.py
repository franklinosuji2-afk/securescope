"""Target repository. Every method takes the organization id; there is no unscoped read."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.billing.errors import PlanLimitError
from app.database.session import make_session_factory
from app.models.target import TargetRow
from app.repositories.plans import lock_organization
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
    # A challenge is usable only with a token and a future expiry; otherwise nothing is shown.
    active = bool(row.challenge_token) and expires is not None and expires > _now()
    token = (row.challenge_token or "") if active else ""
    lapses = verification_expiry(row, valid_days)
    if row.verified_at:
        status = "reverify" if lapses is not None and lapses <= _now() else "verified"
    else:
        status = "pending" if active else "expired"
    return TargetOut(
        id=row.id,
        hostname=row.hostname,
        status=status,
        verification_expires_at=lapses,
        challenge_token=token,
        challenge_expires_at=expires if active else None,
        verified_at=_aware(row.verified_at),
        verification_method=row.verification_method,
        last_check_at=_aware(row.last_check_at),
        last_check_error=row.last_check_error,
        created_at=_aware(row.created_at),
        dns_record_name=dns_record_name(row.hostname),
        dns_record_value=challenge_value(token) if token else "",
        http_file_url=http_file_url(row.hostname),
        http_file_content=challenge_value(token) if token else "",
    )


class TargetRepository:
    def __init__(self, engine: Engine, verification_valid_days: int = 0) -> None:
        self._session = make_session_factory(engine)
        self._valid_days = verification_valid_days

    def create(
        self, organization_id: str, hostname: str, created_by: str, max_websites: int | None = None
    ) -> TargetOut:
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
                if max_websites is not None:
                    # Count and insert under one lock, so simultaneous requests cannot both take the last slot.
                    lock_organization(session, organization_id)
                    used = session.scalar(
                        select(func.count()).select_from(TargetRow).where(TargetRow.organization_id == organization_id)
                    )
                    if int(used or 0) >= max_websites:
                        raise PlanLimitError(
                            f"Your plan includes {max_websites} website{'s' if max_websites != 1 else ''}. "
                            "Remove one or upgrade to add another."
                        )
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

    def clear_challenge(self, target_id: str, organization_id: str) -> TargetOut | None:
        """Remove the active challenge. The target and any existing verification are kept."""
        with self._session.begin() as session:
            row = session.get(TargetRow, target_id, with_for_update=True)
            if row is None or row.organization_id != organization_id:
                return None
            row.challenge_token = None
            row.challenge_expires_at = None
            if row.verified_at is None:
                row.last_check_error = None
            session.flush()
            return to_out(row, self._valid_days)

    def purge_expired_challenges(self) -> int:
        """Erase tokens whose expiry has passed, so a dead value is not kept longer than needed."""
        with self._session.begin() as session:
            result = session.execute(
                update(TargetRow)
                .where(TargetRow.challenge_token.is_not(None), TargetRow.challenge_expires_at <= _now())
                .values(challenge_token=None, challenge_expires_at=None)
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def record_check(
        self,
        target_id: str,
        organization_id: str,
        *,
        method: str,
        error: str | None,
        checked_token: str,
    ) -> TargetOut | None:
        """Store the outcome. A success counts only if the checked token is still the active one."""
        now = _now()
        with self._session.begin() as session:
            row = session.get(TargetRow, target_id, with_for_update=True)
            if row is None or row.organization_id != organization_id:
                return None
            if error is None and (not checked_token or row.challenge_token != checked_token):
                error = "The challenge was replaced or removed while the check ran. Try again with the current value."
            row.last_check_at = now
            row.last_check_error = error
            if error is None:
                row.verified_at = now
                row.verification_method = method
                # The proof is done: the token has no further use, so it is not kept.
                row.challenge_token = None
                row.challenge_expires_at = None
            session.flush()
            return to_out(row, self._valid_days)
