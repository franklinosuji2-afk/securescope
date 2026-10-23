"""API tokens and badges. Every query is limited to one workspace, except the two lookups a caller without a
session must make: a token's digest (CI) and a badge's address (public)."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select

from app.database.session import make_session_factory
from app.models.account import UserRow
from app.models.integration import ApiTokenRow, SiteBadgeRow
from app.models.scan import ScanRow
from app.models.target import TargetRow
from app.schemas.integration import ApiTokenOut, BadgeOut
from app.security.tokens import hash_token

MAX_TOKENS_PER_ORGANIZATION = 5
TOKEN_PREFIX = "ssk_"  # noqa: S105  # nosec B105 (a label, not a secret)
TOUCH_INTERVAL = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@dataclass(frozen=True)
class TokenIdentity:
    token_id: str
    organization_id: str
    user_id: str


@dataclass(frozen=True)
class BadgeSubject:
    organization_id: str
    hostname: str


@dataclass(frozen=True)
class BadgeReading:
    score: int
    grade: str
    scanned_at: datetime | None


def new_api_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


class IntegrationRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    # --- API tokens ------------------------------------------------------------------------------------

    def list_tokens(self, organization_id: str) -> list[ApiTokenOut]:
        with self._session() as session:
            rows = session.execute(
                select(ApiTokenRow, UserRow.email)
                .outerjoin(UserRow, UserRow.id == ApiTokenRow.created_by)
                .where(ApiTokenRow.organization_id == organization_id, ApiTokenRow.revoked_at.is_(None))
                .order_by(ApiTokenRow.created_at)
            ).all()
            return [
                ApiTokenOut(
                    id=t.id,
                    name=t.name,
                    prefix=t.prefix,
                    created_at=_aware(t.created_at),
                    last_used_at=_aware(t.last_used_at),
                    created_by_email=email,
                )
                for t, email in rows
            ]

    def create_token(self, organization_id: str, user_id: str, name: str) -> tuple[ApiTokenOut, str] | None:
        """None when the workspace already has the maximum."""
        token = new_api_token()
        with self._session.begin() as session:
            count = session.scalar(
                select(func.count())
                .select_from(ApiTokenRow)
                .where(ApiTokenRow.organization_id == organization_id, ApiTokenRow.revoked_at.is_(None))
            )
            if (count or 0) >= MAX_TOKENS_PER_ORGANIZATION:
                return None
            row = ApiTokenRow(
                id=uuid.uuid4().hex,
                organization_id=organization_id,
                created_by=user_id,
                name=name,
                token_hash=hash_token(token),
                prefix=token[: len(TOKEN_PREFIX) + 4],
                created_at=_now(),
            )
            session.add(row)
            session.flush()
            out = ApiTokenOut(id=row.id, name=row.name, prefix=row.prefix, created_at=_aware(row.created_at))
            return out, token

    def revoke_token(self, organization_id: str, token_id: str) -> bool:
        with self._session.begin() as session:
            row = session.scalar(
                select(ApiTokenRow).where(
                    ApiTokenRow.id == token_id,
                    ApiTokenRow.organization_id == organization_id,
                    ApiTokenRow.revoked_at.is_(None),
                )
            )
            if row is None:
                return False
            row.revoked_at = _now()
            return True

    def authenticate(self, token: str) -> TokenIdentity | None:
        """The identity behind a token, or None. Revoked tokens and unknown ones look the same."""
        if not token.startswith(TOKEN_PREFIX) or len(token) > 200:
            return None
        with self._session.begin() as session:
            row = session.scalar(
                select(ApiTokenRow).where(
                    ApiTokenRow.token_hash == hash_token(token), ApiTokenRow.revoked_at.is_(None)
                )
            )
            if row is None or row.created_by is None:
                return None
            last = _aware(row.last_used_at)
            if last is None or _now() - last > TOUCH_INTERVAL:
                row.last_used_at = _now()
            return TokenIdentity(row.id, row.organization_id, row.created_by)

    # --- badges ----------------------------------------------------------------------------------------

    def list_badges(self, organization_id: str, base_url: str) -> list[BadgeOut]:
        with self._session() as session:
            rows = session.execute(
                select(TargetRow, SiteBadgeRow.token)
                .outerjoin(SiteBadgeRow, SiteBadgeRow.target_id == TargetRow.id)
                .where(TargetRow.organization_id == organization_id, TargetRow.verified_at.is_not(None))
                .order_by(TargetRow.hostname)
            ).all()
            return [
                BadgeOut(
                    target_id=t.id,
                    hostname=t.hostname,
                    enabled=token is not None,
                    url=badge_url(base_url, token) if token else None,
                )
                for t, token in rows
            ]

    def set_badge(
        self, organization_id: str, target_id: str, enabled: bool, renew: bool
    ) -> str | None | bool:
        """Turns a site's badge on or off. Returns the new token when one was made, True when nothing changed
        in a way that needs a token, and False when the site is not a verified site of this workspace."""
        with self._session.begin() as session:
            target = session.scalar(
                select(TargetRow).where(
                    TargetRow.id == target_id,
                    TargetRow.organization_id == organization_id,
                    TargetRow.verified_at.is_not(None),
                )
            )
            if target is None:
                return False
            row = session.scalar(select(SiteBadgeRow).where(SiteBadgeRow.target_id == target_id))
            if not enabled:
                if row is not None:
                    session.delete(row)
                return True
            token = secrets.token_urlsafe(24)
            if row is None:
                session.add(
                    SiteBadgeRow(
                        id=uuid.uuid4().hex,
                        organization_id=organization_id,
                        target_id=target_id,
                        token=token,
                        created_at=_now(),
                    )
                )
                return token
            if renew:
                row.token = token
                return token
            return True

    def badge_subject(self, token: str) -> BadgeSubject | None:
        if not (16 <= len(token) <= 48):
            return None
        with self._session() as session:
            row = session.execute(
                select(SiteBadgeRow.organization_id, TargetRow.hostname)
                .join(TargetRow, TargetRow.id == SiteBadgeRow.target_id)
                .where(SiteBadgeRow.token == token, TargetRow.verified_at.is_not(None))
            ).first()
            return BadgeSubject(row[0], row[1]) if row else None

    def latest_reading(self, organization_id: str, hostname: str) -> BadgeReading | None:
        with self._session() as session:
            row = session.execute(
                select(ScanRow.score, ScanRow.grade, ScanRow.finished_at)
                .where(
                    ScanRow.organization_id == organization_id,
                    ScanRow.host == hostname,
                    ScanRow.status == "completed",
                    ScanRow.score.is_not(None),
                    ScanRow.grade.is_not(None),
                )
                .order_by(ScanRow.created_at.desc())
                .limit(1)
            ).first()
            if row is None or row[0] is None or row[1] is None:
                return None
            return BadgeReading(int(row[0]), str(row[1]), _aware(row[2]))


def badge_url(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1/badges/{token}.svg"


__all__ = [
    "MAX_TOKENS_PER_ORGANIZATION",
    "BadgeReading",
    "BadgeSubject",
    "IntegrationRepository",
    "TokenIdentity",
    "badge_url",
    "new_api_token",
]
