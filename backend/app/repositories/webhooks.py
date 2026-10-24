"""Webhook endpoints. Every query is limited to one workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import Engine, delete, func, select

from app.database.session import make_session_factory
from app.models.webhook import WebhookDeliveryRow, WebhookEndpointRow
from app.schemas.webhook import WebhookDeliveryOut, WebhookOut

MAX_PER_ORGANIZATION = 3
AUTO_DISABLE_AFTER = 10
# Recent deliveries kept per endpoint.
KEEP_DELIVERIES = 20


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
    kind: str = "webhook"


def _out(row: WebhookEndpointRow) -> WebhookOut:
    return WebhookOut(
        id=row.id,
        kind=row.kind,
        address=address_of(row.url),
        enabled=row.enabled,
        last_attempt_at=_aware(row.last_attempt_at) if row.last_attempt_at else None,
        last_status=row.last_status,
        consecutive_failures=row.consecutive_failures,
        created_at=_aware(row.created_at),
    )


def _endpoint(row: WebhookEndpointRow) -> Endpoint:
    return Endpoint(row.id, row.organization_id, row.url, row.key_version, row.enabled, row.kind)


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
        self, organization_id: str, url: str, user_id: str | None, kind: str = "webhook"
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
                kind=kind,
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

    def record_attempt(
        self,
        webhook_id: str,
        ok: bool,
        status: str,
        *,
        event: str = "unknown",
        delivery_id: str = "",
        attempts: int = 1,
    ) -> None:
        with self._session.begin() as session:
            row = session.get(WebhookEndpointRow, webhook_id)
            if row is None:
                return
            session.add(
                WebhookDeliveryRow(
                    id=uuid.uuid4().hex,
                    webhook_id=webhook_id,
                    delivery_id=delivery_id[:32],
                    event=event[:32],
                    ok=ok,
                    status=status[:120],
                    attempts=attempts,
                    created_at=_now(),
                )
            )
            session.flush()
            keep = session.scalars(
                select(WebhookDeliveryRow.id)
                .where(WebhookDeliveryRow.webhook_id == webhook_id)
                .order_by(WebhookDeliveryRow.created_at.desc(), WebhookDeliveryRow.id)
                .limit(KEEP_DELIVERIES)
            ).all()
            session.execute(
                delete(WebhookDeliveryRow).where(
                    WebhookDeliveryRow.webhook_id == webhook_id, WebhookDeliveryRow.id.not_in(keep)
                )
            )
            row.last_attempt_at = _now()
            row.last_status = status[:120]
            if ok:
                row.consecutive_failures = 0
            else:
                row.consecutive_failures += 1
                if row.consecutive_failures >= AUTO_DISABLE_AFTER:
                    row.enabled = False
            session.flush()

    def deliveries(self, organization_id: str, webhook_id: str) -> list[WebhookDeliveryOut] | None:
        """Recent deliveries, newest first, or None when the endpoint is not this workspace's."""
        with self._session() as session:
            owned = session.scalar(
                select(WebhookEndpointRow.id).where(
                    WebhookEndpointRow.id == webhook_id, WebhookEndpointRow.organization_id == organization_id
                )
            )
            if owned is None:
                return None
            rows = session.scalars(
                select(WebhookDeliveryRow)
                .where(WebhookDeliveryRow.webhook_id == webhook_id)
                .order_by(WebhookDeliveryRow.created_at.desc(), WebhookDeliveryRow.id)
                .limit(KEEP_DELIVERIES)
            )
            return [
                WebhookDeliveryOut(
                    delivery_id=r.delivery_id,
                    event=r.event,
                    ok=r.ok,
                    status=r.status,
                    attempts=r.attempts,
                    created_at=_aware(r.created_at),
                )
                for r in rows
            ]

    def count_all(self) -> int:
        with self._session() as session:
            return int(session.scalar(select(func.count()).select_from(WebhookEndpointRow)) or 0)


__all__ = [
    "AUTO_DISABLE_AFTER",
    "KEEP_DELIVERIES",
    "MAX_PER_ORGANIZATION",
    "Endpoint",
    "WebhookRepository",
    "address_of",
]
