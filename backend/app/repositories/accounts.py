"""Persistence for users, organizations, memberships, sessions, one-time tokens and audit events."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.session import make_session_factory
from app.models.account import (
    AccountTokenRow,
    AuditEventRow,
    MemberRow,
    OrganizationRow,
    SessionRow,
    UserRow,
)
from app.schemas.audit import AuditEntry
from app.security.permissions import Role
from app.security.tokens import hash_token


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _id() -> str:
    return uuid.uuid4().hex


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "org"
    return f"{base}-{secrets.token_hex(3)}"


class DuplicateEmailError(Exception):
    pass


class LastOwnerError(Exception):
    pass


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    password_hash: str
    email_verified: bool
    active: bool


@dataclass(frozen=True)
class OrgMembership:
    organization_id: str
    name: str
    slug: str
    role: Role


@dataclass(frozen=True)
class MemberRecord:
    user_id: str
    email: str
    role: Role
    joined_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    id: str
    user_id: str
    csrf_token: str
    expires_at: datetime


def _user(row: UserRow) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        email_verified=row.email_verified_at is not None,
        active=row.account_status == "ACTIVE",
    )


class AccountRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    # --- users ------------------------------------------------------------------------

    def create_user_with_org(
        self, email: str, password_hash: str, org_name: str
    ) -> tuple[UserRecord, OrgMembership]:
        """Creates the user plus a personal organization they own, atomically."""
        now = _now()
        user_id, org_id = _id(), _id()
        try:
            with self._session.begin() as session:
                session.add(
                    UserRow(
                        id=user_id,
                        email=email,
                        password_hash=password_hash,
                        account_status="ACTIVE",
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.add(
                    OrganizationRow(
                        id=org_id,
                        name=org_name,
                        slug=slugify(org_name),
                        status="ACTIVE",
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.flush()
                session.add(
                    MemberRow(
                        id=_id(),
                        organization_id=org_id,
                        user_id=user_id,
                        role=Role.OWNER.value,
                        created_at=now,
                    )
                )
        except IntegrityError as exc:
            raise DuplicateEmailError from exc
        user = self.get_user(user_id)
        if user is None:
            raise RuntimeError("user vanished immediately after creation")
        return user, self.membership(org_id, user_id)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._session() as session:
            row = session.get(UserRow, user_id)
            return _user(row) if row else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        with self._session() as session:
            row = session.scalar(select(UserRow).where(UserRow.email == email))
            return _user(row) if row else None

    def set_password(self, user_id: str, password_hash: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(password_hash=password_hash, updated_at=_now())
            )

    def mark_email_verified(self, user_id: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(UserRow)
                .where(UserRow.id == user_id)
                .values(email_verified_at=_now(), updated_at=_now())
            )

    # --- organizations ----------------------------------------------------------------

    def create_org(self, name: str, owner_id: str) -> OrgMembership:
        now = _now()
        org_id = _id()
        with self._session.begin() as session:
            session.add(
                OrganizationRow(
                    id=org_id, name=name, slug=slugify(name), status="ACTIVE", created_at=now, updated_at=now
                )
            )
            session.flush()
            session.add(
                MemberRow(
                    id=_id(), organization_id=org_id, user_id=owner_id, role=Role.OWNER.value, created_at=now
                )
            )
        return self.membership(org_id, owner_id)  # type: ignore[return-value]

    def memberships_for_user(self, user_id: str) -> list[OrgMembership]:
        with self._session() as session:
            rows = session.execute(
                select(OrganizationRow, MemberRow.role)
                .join(MemberRow, MemberRow.organization_id == OrganizationRow.id)
                .where(MemberRow.user_id == user_id, OrganizationRow.status == "ACTIVE")
                .order_by(MemberRow.created_at, OrganizationRow.id)
            ).all()
            return [OrgMembership(o.id, o.name, o.slug, Role(r)) for o, r in rows]

    def membership(self, organization_id: str, user_id: str) -> OrgMembership | None:
        for item in self.memberships_for_user(user_id):
            if item.organization_id == organization_id:
                return item
        return None

    def list_members(self, organization_id: str) -> list[MemberRecord]:
        with self._session() as session:
            rows = session.execute(
                select(MemberRow, UserRow.email)
                .join(UserRow, UserRow.id == MemberRow.user_id)
                .where(MemberRow.organization_id == organization_id)
                .order_by(MemberRow.created_at, MemberRow.id)
            ).all()
            return [MemberRecord(m.user_id, e, Role(m.role), _aware(m.created_at)) for m, e in rows]

    def _owner_count(self, session: Session, organization_id: str) -> int:
        return (
            session.scalar(
                select(func.count())
                .select_from(MemberRow)
                .where(MemberRow.organization_id == organization_id, MemberRow.role == Role.OWNER.value)
            )
            or 0
        )

    def add_member(self, organization_id: str, user_id: str, role: Role) -> bool:
        """Returns False if the user is already a member."""
        try:
            with self._session.begin() as session:
                session.add(
                    MemberRow(
                        id=_id(),
                        organization_id=organization_id,
                        user_id=user_id,
                        role=role.value,
                        created_at=_now(),
                    )
                )
        except IntegrityError:
            return False
        return True

    def set_member_role(self, organization_id: str, user_id: str, role: Role) -> bool:
        with self._session.begin() as session:
            row = session.scalar(
                select(MemberRow).where(
                    MemberRow.organization_id == organization_id, MemberRow.user_id == user_id
                )
            )
            if row is None:
                return False
            if row.role == Role.OWNER.value and role is not Role.OWNER:
                if self._owner_count(session, organization_id) <= 1:
                    raise LastOwnerError
            row.role = role.value
            return True

    def remove_member(self, organization_id: str, user_id: str) -> bool:
        with self._session.begin() as session:
            row = session.scalar(
                select(MemberRow).where(
                    MemberRow.organization_id == organization_id, MemberRow.user_id == user_id
                )
            )
            if row is None:
                return False
            if row.role == Role.OWNER.value and self._owner_count(session, organization_id) <= 1:
                raise LastOwnerError
            session.delete(row)
            return True

    # --- sessions ---------------------------------------------------------------------

    def create_session(self, user_id: str, token: str, csrf_token: str, ttl: timedelta) -> SessionRecord:
        now = _now()
        row = SessionRow(
            id=_id(),
            user_id=user_id,
            token_hash=hash_token(token),
            csrf_token=csrf_token,
            created_at=now,
            expires_at=now + ttl,
        )
        with self._session.begin() as session:
            session.add(row)
        return SessionRecord(row.id, user_id, csrf_token, row.expires_at)

    def get_session(self, token: str) -> SessionRecord | None:
        with self._session() as session:
            row = session.scalar(select(SessionRow).where(SessionRow.token_hash == hash_token(token)))
            if row is None or row.revoked_at is not None or _aware(row.expires_at) <= _now():
                return None
            return SessionRecord(row.id, row.user_id, row.csrf_token, _aware(row.expires_at))

    def revoke_session(self, session_id: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(SessionRow)
                .where(SessionRow.id == session_id, SessionRow.revoked_at.is_(None))
                .values(revoked_at=_now())
            )

    def revoke_all_sessions(self, user_id: str) -> int:
        with self._session.begin() as session:
            result = session.execute(
                update(SessionRow)
                .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def purge_expired_sessions(self) -> int:
        cutoff = _now() - timedelta(days=1)
        with self._session.begin() as session:
            result = session.execute(delete(SessionRow).where(SessionRow.expires_at < cutoff))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # --- one-time tokens --------------------------------------------------------------

    def create_account_token(self, user_id: str, kind: str, token: str, ttl: timedelta) -> None:
        now = _now()
        with self._session.begin() as session:
            session.add(
                AccountTokenRow(
                    id=_id(),
                    user_id=user_id,
                    kind=kind,
                    token_hash=hash_token(token),
                    created_at=now,
                    expires_at=now + ttl,
                )
            )

    def consume_account_token(self, kind: str, token: str) -> str | None:
        """Marks a valid token used and returns its user id. Single use, atomic."""
        now = _now()
        with self._session.begin() as session:
            row = session.scalar(
                select(AccountTokenRow).where(
                    AccountTokenRow.token_hash == hash_token(token), AccountTokenRow.kind == kind
                )
            )
            if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
                return None
            claimed = session.execute(
                update(AccountTokenRow)
                .where(AccountTokenRow.id == row.id, AccountTokenRow.used_at.is_(None))
                .values(used_at=now)
            )
            return row.user_id if claimed.rowcount == 1 else None  # type: ignore[attr-defined]


class AuditRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def record(
        self,
        event_type: str,
        *,
        organization_id: str | None = None,
        actor_user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        with self._session.begin() as session:
            session.add(
                AuditEventRow(
                    id=_id(),
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    event_type=event_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    request_id=request_id,
                    timestamp=_now(),
                )
            )

    def list_events(self, organization_id: str, limit: int = 100) -> list[AuditEventRow]:
        with self._session() as session:
            return list(
                session.scalars(
                    select(AuditEventRow)
                    .where(AuditEventRow.organization_id == organization_id)
                    .order_by(AuditEventRow.timestamp.desc())
                    .limit(limit)
                )
            )

    def query_events(
        self, organization_id: str, *, limit: int, offset: int, event_type: str | None = None
    ) -> tuple[list[AuditEntry], int]:
        """Newest first. Only events of `organization_id` are ever visible (tenant isolation)."""
        scope = [AuditEventRow.organization_id == organization_id]
        if event_type:
            scope.append(AuditEventRow.event_type == event_type)
        with self._session() as session:
            total = session.scalar(select(func.count()).select_from(AuditEventRow).where(*scope)) or 0
            rows = session.execute(
                select(AuditEventRow, UserRow.email)
                .outerjoin(UserRow, UserRow.id == AuditEventRow.actor_user_id)
                .where(*scope)
                .order_by(AuditEventRow.timestamp.desc(), AuditEventRow.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            items = [
                AuditEntry(
                    id=row.id,
                    timestamp=_aware(row.timestamp),
                    event_type=row.event_type,
                    actor_user_id=row.actor_user_id,
                    actor_email=email,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    request_id=row.request_id,
                )
                for row, email in rows
            ]
        return items, total

    def event_types(self, organization_id: str) -> list[str]:
        with self._session() as session:
            return list(
                session.scalars(
                    select(AuditEventRow.event_type)
                    .where(AuditEventRow.organization_id == organization_id)
                    .distinct()
                    .order_by(AuditEventRow.event_type)
                )
            )

    def all_event_types(self) -> list[str]:
        with self._session() as session:
            return list(session.scalars(select(AuditEventRow.event_type).order_by(AuditEventRow.timestamp)))
