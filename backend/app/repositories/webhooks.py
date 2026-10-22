"""Webhook endpoints. Every query is limited to one workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import Engine, func, select

from app.database.session import make_session_factory
from app.models.webhook import WebhookEndpointRow
from app.schemas.webhook import WebhookOut

MAX_PER_ORGANIZATION = 3
AUTO_DISABLE_AFTER = 10


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def address_of(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    shown = f"[{host}]" if ":" in host else host
    port = f":{parts.port}" if parts.port not in (None, 443) else ""
    return f"{parts.scheme}://{shown}{port}/…"


@dataclass(frozen=True)
class Endpoint:
    id: str
    organization_id: str
    url: str
    key_version: int
    enabled: bool


def _out(row: WebhookEndpointRow) -> WebhookOut:
    return WebhookOut(
        id=row.id,
        address=address_of(row.url),
        enabled=row.enabled,
        last_attempt_at=_aware(row.last_attempt_at) if row.last_attempt_at else None,
        last_status=row.last_status,
        consecutive_failures=row.consecutive_failures,
        created_at=_aware(row.created_at),
    )


def _endpoint(row: WebhookEndpointRow) -> Endpoint:
    return Endpoint(row.id, row.organization_id, row.url, row.key_version, row.enabled)


class WebhookRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    def list_for_organization(self, organization_id: str) -> list[WebhookOut]:
        with self._session() as session:
            rows = session.scalars(
                select(WebhookEndpointRow)
                .where(WebhookEndpointRow.organization_id == organization_id)
                .order_by(WebhookEndpointRow.created_at)
            )
            return [_out(r) for r in rows]

    def endpoints(self, organization_id: str, *, only_enabled: bool = False) -> list[Endpoint]:
        with self._session() as session:
            query = select(WebhookEndpointRow).where(WebhookEndpointRow.organization_id == organization_id)
            if only_enabled:
                query = query.where(WebhookEndpointRow.enabled.is_(True))
            return [_endpoint(r) for r in session.scalars(query.order_by(WebhookEndpointRow.created_at))]

    def get(self, organization_id: str, webhook_id: str) -> Endpoint | None:
        with self._session() as session:
            row = session.scalar(
                select(WebhookEndpointRow).where(
                    WebhookEndpointRow.id == webhook_id, WebhookEndpointRow.organization_id == organization_id
                )
            )
            return _endpoint(row) if row else None

    def create(
        self, organization_id: str, url: str, user_id: str | None
    ) -> tuple[Endpoint, WebhookOut] | None:
        """None when the workspace already has the maximum."""
        with self._session.begin() as session:
            count = session.scalar(
                select(func.count())
                .select_from(WebhookEndpointRow)
                .where(WebhookEndpointRow.organization_id == organization_id)
            )
            if (count or 0) >= MAX_PER_ORGANIZATION:
                return None
            row = WebhookEndpointRow(
                id=uuid.uuid4().hex,
                organization_id=organization_id,
                url=url,
                key_version=1,
                enabled=True,
                consecutive_failures=0,
                created_by=user_id,
                created_at=_now(),
            )
            session.add(row)
            session.flush()
            return _endpoint(row), _out(row)

    def rotate(self, organization_id: str, webhook_id: str) -> Endpoint | None:
        with self._session.begin() as session:
            row = session.scalar(
                select(WebhookEndpointRow).where(
                    WebhookEndpointRow.id == webhook_id, WebhookEndpointRow.organization_id == organization_id
                )
            )
            if row is None:
                return None
            row.key_version += 1
            session.flush()
            return _endpoint(row)

    def set_enabled(self, organization_id: str, webhook_id: str, enabled: bool) -> WebhookOut | None:
        with self._session.begin() as session:
            row = session.scalar(
                select(WebhookEndpointRow).where(
                    WebhookEndpointRow.id == webhook_id, WebhookEndpointRow.organization_id == organization_id
                )
            )
            if row is None:
                return None
            row.enabled = enabled
            if enabled:
                row.consecutive_failures = 0
            session.flush()
            return _out(row)

    def delete(self, organization_id: str, webhook_id: str) -> bool:
        with self._session.begin() as session:
            row = session.scalar(
                select(WebhookEndpointRow).where(
                    WebhookEndpointRow.id == webhook_id, WebhookEndpointRow.organization_id == organization_id
                )
            )
            if row is None:
                return False
            session.delete(row)
            return True

    def record_attempt(self, webhook_id: str, ok: bool, status: str) -> None:
        with self._session.begin() as session:
            row = session.get(WebhookEndpointRow, webhook_id)
            if row is None:
                return
            row.last_attempt_at = _now()
            row.last_status = status[:120]
            if ok:
                row.consecutive_failures = 0
            else:
                row.consecutive_failures += 1
                if row.consecutive_failures >= AUTO_DISABLE_AFTER:
                    row.enabled = False
            session.flush()

    def count_all(self) -> int:
        with self._session() as session:
            return int(session.scalar(select(func.count()).select_from(WebhookEndpointRow)) or 0)


__all__ = ["AUTO_DISABLE_AFTER", "MAX_PER_ORGANIZATION", "Endpoint", "WebhookRepository", "address_of"]
