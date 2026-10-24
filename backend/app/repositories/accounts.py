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
    InvitationRow,
    MemberRow,
    OAuthIdentityRow,
    OAuthStateRow,
    OrganizationRow,
    SessionRow,
    UserRow,
)
from app.models.scan import FindingRow, FindingStateRow, ReportRow, ScanRow
from app.models.target import TargetRow
from app.schemas.audit import AuditEntry
from app.security.permissions import Role
from app.security.tokens import constant_time_equal, hash_token


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _id() -> str:
    return uuid.uuid4().hex


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "org"
    return f"{base}-{secrets.token_hex(3)}"


# Stored for accounts that have no password (sign-in through a provider only). It is not a valid hash,
# so no password can ever match it.
UNUSABLE_PASSWORD = "!"  # noqa: S105  # nosec B105


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
class InvitationRecord:
    id: str
    organization_id: str
    organization_name: str
    email: str
    role: Role
    invited_by_email: str | None
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class InvitationAcceptance:
    """`status` is "ok", "invalid" (unknown, used, revoked, expired) or "wrong_email"."""

    status: str
    organization_id: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    id: str
    user_id: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionInfo:
    """What the person may see about one of their own sign-ins. Never the token or its digest."""

    id: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class AccountDetails:
    created_at: datetime
    status: str


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

    def revoke_other_sessions(self, user_id: str, keep_session_id: str) -> int:
        with self._session.begin() as session:
            result = session.execute(
                update(SessionRow)
                .where(
                    SessionRow.user_id == user_id,
                    SessionRow.id != keep_session_id,
                    SessionRow.revoked_at.is_(None),
                )
                .values(revoked_at=_now())
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def list_sessions(self, user_id: str) -> list[SessionInfo]:
        """The person's sign-ins that are still usable, newest first."""
        now = _now()
        with self._session() as session:
            rows = session.scalars(
                select(SessionRow)
                .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
                .order_by(SessionRow.created_at.desc())
            ).all()
            return [
                SessionInfo(r.id, _aware(r.created_at), _aware(r.expires_at))
                for r in rows
                if _aware(r.expires_at) > now
            ]

    def revoke_user_session(self, user_id: str, session_id: str) -> bool:
        """Signs out one device. Only a session that belongs to `user_id` can be revoked."""
        with self._session.begin() as session:
            result = session.execute(
                update(SessionRow)
                .where(
                    SessionRow.id == session_id,
                    SessionRow.user_id == user_id,
                    SessionRow.revoked_at.is_(None),
                )
                .values(revoked_at=_now())
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def account_details(self, user_id: str) -> AccountDetails | None:
        with self._session() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            return AccountDetails(_aware(row.created_at), row.account_status)

    def export_personal_data(self, user_id: str) -> dict[str, object]:
        """Everything about this person, for them to keep. It holds no password hash, no token or digest, and
        nothing that belongs to another customer. Other members and the workspace's websites are not listed, because
        a client viewer must not learn what other clients of an agency scan."""
        with self._session() as session:
            user = session.get(UserRow, user_id)
            if user is None:
                return {}
            memberships = session.execute(
                select(OrganizationRow, MemberRow.role, MemberRow.created_at)
                .join(MemberRow, MemberRow.organization_id == OrganizationRow.id)
                .where(MemberRow.user_id == user_id)
                .order_by(MemberRow.created_at)
            ).all()
            identities = session.scalars(
                select(OAuthIdentityRow).where(OAuthIdentityRow.user_id == user_id)
            ).all()
            events = session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.actor_user_id == user_id)
                .order_by(AuditEventRow.timestamp)
                .limit(5000)
            ).all()
            workspaces: list[dict[str, object]] = []
            for org, role, joined in memberships:
                workspaces.append(
                    {
                        "name": org.name,
                        "your_role": role,
                        "joined": _aware(joined).isoformat(),
                    }
                )
            return {
                "exported_at": _now().isoformat(),
                "account": {
                    "email": user.email,
                    "email_verified": user.email_verified_at is not None,
                    "status": user.account_status,
                    "created": _aware(user.created_at).isoformat(),
                    "has_password": user.password_hash != UNUSABLE_PASSWORD,
                },
                "sign_in_providers": [
                    {"provider": i.provider, "email": i.email, "linked": _aware(i.created_at).isoformat()}
                    for i in identities
                ],
                "workspaces": workspaces,
                "actions_recorded_in_the_audit_log": [
                    {
                        "time": _aware(e.timestamp).isoformat(),
                        "event": e.event_type,
                        "resource_type": e.resource_type,
                    }
                    for e in events
                ],
                "note": "Websites, scan results and reports belong to the workspace and are exported from its pages in the app.",
            }

    # --- deleting an account ----------------------------------------------------------

    def organizations_blocking_deletion(self, user_id: str) -> list[str]:
        """Names of workspaces this person owns alone while other people still belong to them.

        Deleting the account would leave those people without an owner, so the person must hand over
        ownership or remove the members first.
        """
        with self._session() as session:
            blocking: list[str] = []
            memberships = session.scalars(select(MemberRow).where(MemberRow.user_id == user_id)).all()
            for membership in memberships:
                if membership.role != Role.OWNER.value:
                    continue
                members = session.scalar(
                    select(func.count()).select_from(MemberRow).where(
                        MemberRow.organization_id == membership.organization_id
                    )
                )
                if (members or 0) > 1 and self._owner_count(session, membership.organization_id) <= 1:
                    org = session.get(OrganizationRow, membership.organization_id)
                    blocking.append(org.name if org else membership.organization_id)
            return blocking

    def delete_account(self, user_id: str) -> None:
        """Erases the account. A workspace nobody else belongs to is erased with everything in it (sites,
        scans, findings, reports, invitations, its audit log); in a shared workspace only this person's
        membership goes. Deletes are explicit so behaviour does not depend on the database enforcing FKs."""
        with self._session.begin() as session:
            memberships = session.scalars(select(MemberRow).where(MemberRow.user_id == user_id)).all()
            for membership in memberships:
                org_id = membership.organization_id
                members = session.scalar(
                    select(func.count()).select_from(MemberRow).where(MemberRow.organization_id == org_id)
                )
                if (members or 0) > 1:
                    continue
                scan_ids = select(ScanRow.id).where(ScanRow.organization_id == org_id)
                session.execute(delete(ReportRow).where(ReportRow.organization_id == org_id))
                session.execute(delete(FindingRow).where(FindingRow.scan_id.in_(scan_ids)))
                session.execute(delete(ScanRow).where(ScanRow.organization_id == org_id))
                session.execute(delete(FindingStateRow).where(FindingStateRow.organization_id == org_id))
                session.execute(delete(TargetRow).where(TargetRow.organization_id == org_id))
                session.execute(delete(InvitationRow).where(InvitationRow.organization_id == org_id))
                session.execute(delete(AuditEventRow).where(AuditEventRow.organization_id == org_id))
                session.execute(delete(MemberRow).where(MemberRow.organization_id == org_id))
                session.execute(delete(OrganizationRow).where(OrganizationRow.id == org_id))
            session.execute(delete(MemberRow).where(MemberRow.user_id == user_id))
            # What this person did in workspaces that continue stays, but no longer points at them.
            for model, column in (
                (ScanRow, "requested_by"),
                (TargetRow, "created_by"),
                (FindingStateRow, "updated_by"),
                (ReportRow, "generated_by"),
                (InvitationRow, "invited_by"),
                (AuditEventRow, "actor_user_id"),
            ):
                session.execute(update(model).where(getattr(model, column) == user_id).values({column: None}))
            session.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
            session.execute(delete(AccountTokenRow).where(AccountTokenRow.user_id == user_id))
            session.execute(delete(OAuthIdentityRow).where(OAuthIdentityRow.user_id == user_id))
            session.execute(delete(UserRow).where(UserRow.id == user_id))

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


    # --- sign in with an outside provider ---------------------------------------------

    def find_identity_user_id(self, provider: str, subject: str) -> str | None:
        with self._session() as session:
            return session.scalar(
                select(OAuthIdentityRow.user_id).where(
                    OAuthIdentityRow.provider == provider, OAuthIdentityRow.subject == subject
                )
            )

    def link_identity(self, user_id: str, provider: str, subject: str, email: str) -> None:
        with self._session.begin() as session:
            session.add(
                OAuthIdentityRow(
                    id=_id(), user_id=user_id, provider=provider, subject=subject, email=email, created_at=_now()
                )
            )

    def create_oauth_user_with_org(
        self, email: str, org_name: str, provider: str, subject: str
    ) -> tuple[UserRecord, OrgMembership]:
        """A new account without a password, its email already confirmed by the provider, plus a workspace."""
        user, membership = self.create_user_with_org(email, UNUSABLE_PASSWORD, org_name)
        self.mark_email_verified(user.id)
        self.link_identity(user.id, provider, subject, email)
        refreshed = self.get_user(user.id)
        return (refreshed or user), membership

    def take_over_unconfirmed_account(self, user_id: str) -> None:
        """The email was never confirmed, so whoever set its password may not be the owner. Remove the
        password and end every session before the real owner's provider sign-in is linked."""
        self.set_password(user_id, UNUSABLE_PASSWORD)
        self.revoke_all_sessions(user_id)
        self.mark_email_verified(user_id)

    def create_oauth_state(
        self, state: str, browser: str, provider: str, code_verifier: str, ttl: timedelta
    ) -> None:
        with self._session.begin() as session:
            session.add(
                OAuthStateRow(
                    state_hash=hash_token(state),
                    browser_hash=hash_token(browser),
                    provider=provider,
                    code_verifier=code_verifier,
                    expires_at=_now() + ttl,
                )
            )

    def consume_oauth_state(self, state: str, browser: str, provider: str) -> str | None:
        """Single use. Returns the PKCE verifier only if the state is fresh, was issued for this provider and
        for this browser (the cookie). The row is deleted whatever the outcome."""
        with self._session.begin() as session:
            row = session.get(OAuthStateRow, hash_token(state))
            if row is None:
                return None
            verifier = row.code_verifier
            ok = (
                _aware(row.expires_at) > _now()
                and row.provider == provider
                and constant_time_equal(row.browser_hash, hash_token(browser))
            )
            session.delete(row)
            return verifier if ok else None

    def purge_expired_oauth_states(self) -> int:
        with self._session.begin() as session:
            result = session.execute(delete(OAuthStateRow).where(OAuthStateRow.expires_at < _now()))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # --- invitations ------------------------------------------------------------------

    def _open_invitation_filter(self, now: datetime):  # type: ignore[no-untyped-def]
        return (
            InvitationRow.accepted_at.is_(None),
            InvitationRow.revoked_at.is_(None),
            InvitationRow.expires_at > now,
        )

    def _invitation_record(self, session: Session, row: InvitationRow) -> InvitationRecord:
        org = session.get(OrganizationRow, row.organization_id)
        inviter = session.get(UserRow, row.invited_by) if row.invited_by else None
        return InvitationRecord(
            id=row.id,
            organization_id=row.organization_id,
            organization_name=org.name if org else "",
            email=row.email,
            role=Role(row.role),
            invited_by_email=inviter.email if inviter else None,
            created_at=_aware(row.created_at),
            expires_at=_aware(row.expires_at),
        )

    def create_invitation(
        self, organization_id: str, email: str, role: Role, invited_by: str, token: str, ttl: timedelta
    ) -> InvitationRecord:
        """Stores a new invitation. Any earlier open one for the same address is revoked, so only the newest link works."""
        now = _now()
        address = email.strip().lower()
        with self._session.begin() as session:
            session.execute(
                update(InvitationRow)
                .where(
                    InvitationRow.organization_id == organization_id,
                    InvitationRow.email == address,
                    *self._open_invitation_filter(now),
                )
                .values(revoked_at=now)
            )
            row = InvitationRow(
                id=_id(),
                organization_id=organization_id,
                email=address,
                role=role.value,
                token_hash=hash_token(token),
                invited_by=invited_by,
                created_at=now,
                expires_at=now + ttl,
            )
            session.add(row)
            session.flush()
            return self._invitation_record(session, row)

    def list_pending_invitations(self, organization_id: str) -> list[InvitationRecord]:
        now = _now()
        with self._session() as session:
            rows = session.scalars(
                select(InvitationRow)
                .where(InvitationRow.organization_id == organization_id, *self._open_invitation_filter(now))
                .order_by(InvitationRow.created_at.desc(), InvitationRow.id)
            ).all()
            return [self._invitation_record(session, row) for row in rows]

    def revoke_invitation(self, organization_id: str, invitation_id: str) -> bool:
        now = _now()
        with self._session.begin() as session:
            result = session.execute(
                update(InvitationRow)
                .where(
                    InvitationRow.id == invitation_id,
                    InvitationRow.organization_id == organization_id,
                    *self._open_invitation_filter(now),
                )
                .values(revoked_at=now)
            )
            return bool(result.rowcount)  # type: ignore[attr-defined]

    def open_invitation(self, token: str) -> InvitationRecord | None:
        """The invitation behind a link, if it can still be used."""
        now = _now()
        with self._session() as session:
            row = session.scalar(
                select(InvitationRow).where(
                    InvitationRow.token_hash == hash_token(token), *self._open_invitation_filter(now)
                )
            )
            org = session.get(OrganizationRow, row.organization_id) if row else None
            if row is None or org is None or org.status != "ACTIVE":
                return None
            return self._invitation_record(session, row)

    def accept_invitation(self, token: str, user_id: str, user_email: str) -> InvitationAcceptance:
        """Single use and atomic. The account's email must be the address that was invited."""
        now = _now()
        with self._session.begin() as session:
            row = session.scalar(select(InvitationRow).where(InvitationRow.token_hash == hash_token(token)))
            org = session.get(OrganizationRow, row.organization_id) if row else None
            if (
                row is None
                or org is None
                or org.status != "ACTIVE"
                or row.accepted_at is not None
                or row.revoked_at is not None
                or _aware(row.expires_at) <= now
            ):
                return InvitationAcceptance("invalid")
            if row.email.lower() != user_email.strip().lower():
                return InvitationAcceptance("wrong_email")
            claimed = session.execute(
                update(InvitationRow)
                .where(
                    InvitationRow.id == row.id,
                    InvitationRow.accepted_at.is_(None),
                    InvitationRow.revoked_at.is_(None),
                )
                .values(accepted_at=now)
            )
            if claimed.rowcount != 1:  # type: ignore[attr-defined]
                return InvitationAcceptance("invalid")
            already = session.scalar(
                select(MemberRow.id).where(
                    MemberRow.organization_id == row.organization_id, MemberRow.user_id == user_id
                )
            )
            if already is None:
                try:
                    with session.begin_nested():
                        session.add(
                            MemberRow(
                                id=_id(),
                                organization_id=row.organization_id,
                                user_id=user_id,
                                role=row.role,
                                created_at=now,
                            )
                        )
                except IntegrityError:
                    pass  # joined by another route at the same moment; the invitation is still used up
            return InvitationAcceptance("ok", row.organization_id)

    def purge_old_invitations(self) -> int:
        """Invitations live at most a week, so anything a month past its expiry is gone for good."""
        with self._session.begin() as session:
            result = session.execute(
                delete(InvitationRow).where(InvitationRow.expires_at < _now() - timedelta(days=30))
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]


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
