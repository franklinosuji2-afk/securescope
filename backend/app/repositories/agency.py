"""Clients, branding and shared report links. Every query is limited to one organization."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError

from app.database.session import make_session_factory
from app.models.agency import ClientRow, OrganizationBrandingRow, ReportShareRow
from app.models.scan import ReportRow, ScanRow
from app.models.target import TargetRow
from app.schemas.agency import ClientOut, ShareOut
from app.schemas.scan import ScanStatus


class DuplicateClientError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_out(row: ClientRow, sites: int = 0) -> ClientOut:
    return ClientOut(
        id=row.id,
        name=row.name,
        contact_email=row.contact_email,
        notes=row.notes,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        site_count=sites,
    )


def _share_out(row: ReportShareRow, now: datetime) -> ShareOut:
    expires = _aware(row.expires_at)
    status = "revoked" if row.revoked_at else "expired" if expires <= now else "active"
    return ShareOut(
        id=row.id,
        created_at=_aware(row.created_at),
        expires_at=expires,
        revoked_at=_aware(row.revoked_at) if row.revoked_at else None,
        last_viewed_at=_aware(row.last_viewed_at) if row.last_viewed_at else None,
        view_count=row.view_count,
        status=status,
    )


class AgencyRepository:
    def __init__(self, engine: Engine) -> None:
        self._session = make_session_factory(engine)

    # --- clients ---------------------------------------------------------------------------------

    def list_clients(self, organization_id: str) -> list[ClientOut]:
        with self._session() as session:
            counts = {
                client_id: int(total)
                for client_id, total in session.execute(
                    select(TargetRow.client_id, func.count())
                    .where(TargetRow.organization_id == organization_id, TargetRow.client_id.is_not(None))
                    .group_by(TargetRow.client_id)
                ).all()
            }
            rows = session.scalars(
                select(ClientRow).where(ClientRow.organization_id == organization_id).order_by(ClientRow.name)
            ).all()
            return [_client_out(r, counts.get(r.id, 0)) for r in rows]

    def get_client(self, client_id: str, organization_id: str) -> ClientOut | None:
        with self._session() as session:
            row = session.get(ClientRow, client_id)
            if row is None or row.organization_id != organization_id:
                return None
            sites = session.scalar(
                select(func.count()).select_from(TargetRow).where(TargetRow.client_id == row.id)
            )
            return _client_out(row, int(sites or 0))

    def create_client(
        self, organization_id: str, name: str, contact_email: str | None, notes: str | None
    ) -> ClientOut:
        now = _now()
        row = ClientRow(
            id=uuid.uuid4().hex,
            organization_id=organization_id,
            name=name,
            contact_email=contact_email,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._session.begin() as session:
                session.add(row)
                session.flush()
                return _client_out(row)
        except IntegrityError as exc:
            raise DuplicateClientError from exc

    def update_client(
        self, client_id: str, organization_id: str, name: str, contact_email: str | None, notes: str | None
    ) -> ClientOut | None:
        try:
            with self._session.begin() as session:
                row = session.get(ClientRow, client_id)
                if row is None or row.organization_id != organization_id:
                    return None
                row.name, row.contact_email, row.notes, row.updated_at = name, contact_email, notes, _now()
                session.flush()
                sites = session.scalar(
                    select(func.count()).select_from(TargetRow).where(TargetRow.client_id == row.id)
                )
                return _client_out(row, int(sites or 0))
        except IntegrityError as exc:
            raise DuplicateClientError from exc

    def delete_client(self, client_id: str, organization_id: str) -> bool:
        """Removes the client. Its websites stay in the workspace, unassigned."""
        with self._session.begin() as session:
            row = session.get(ClientRow, client_id)
            if row is None or row.organization_id != organization_id:
                return False
            session.execute(
                update(TargetRow)
                .where(TargetRow.client_id == client_id, TargetRow.organization_id == organization_id)
                .values(client_id=None)
            )
            session.delete(row)
            return True

    def assign_target(self, target_id: str, organization_id: str, client_id: str | None) -> bool:
        """False when the site or the client is not in this organization (or does not exist)."""
        with self._session.begin() as session:
            target = session.get(TargetRow, target_id)
            if target is None or target.organization_id != organization_id:
                return False
            if client_id is not None:
                client = session.get(ClientRow, client_id)
                if client is None or client.organization_id != organization_id:
                    return False
            target.client_id = client_id
            return True

    def targets_with_clients(self, organization_id: str) -> list[tuple[TargetRow, str | None]]:
        with self._session() as session:
            rows = session.scalars(
                select(TargetRow)
                .where(TargetRow.organization_id == organization_id)
                .order_by(TargetRow.hostname)
            ).all()
            session.expunge_all()
            return [(r, r.client_id) for r in rows]

    def latest_completed_scans(self, organization_id: str, hosts: list[str]) -> dict[str, str]:
        """Newest completed scan id per host, for this organization only."""
        if not hosts:
            return {}
        with self._session() as session:
            rows = session.execute(
                select(ScanRow.host, ScanRow.id)
                .where(
                    ScanRow.organization_id == organization_id,
                    ScanRow.status == ScanStatus.COMPLETED.value,
                    ScanRow.host.in_(hosts),
                )
                .order_by(ScanRow.created_at.desc(), ScanRow.id.desc())
            ).all()
        latest: dict[str, str] = {}
        for host, scan_id in rows:
            latest.setdefault(host, scan_id)
        return latest

    # --- branding --------------------------------------------------------------------------------

    def agency_name(self, organization_id: str) -> str | None:
        with self._session() as session:
            row = session.get(OrganizationBrandingRow, organization_id)
            return row.agency_name if row else None

    def set_agency_name(self, organization_id: str, name: str | None) -> None:
        with self._session.begin() as session:
            row = session.get(OrganizationBrandingRow, organization_id)
            if row is None:
                session.add(
                    OrganizationBrandingRow(
                        organization_id=organization_id, agency_name=name, updated_at=_now()
                    )
                )
            else:
                row.agency_name, row.updated_at = name, _now()

    # --- shared report links ---------------------------------------------------------------------

    def create_share(
        self, organization_id: str, scan_id: str, user_id: str, days: int
    ) -> tuple[ShareOut, str]:
        """Makes a link for a scan of this organization. The secret is returned once and never stored."""
        token = secrets.token_urlsafe(32)
        now = _now()
        row = ReportShareRow(
            id=uuid.uuid4().hex,
            organization_id=organization_id,
            scan_id=scan_id,
            token_hash=hash_token(token),
            created_by=user_id,
            created_at=now,
            expires_at=now + timedelta(days=days),
            view_count=0,
        )
        with self._session.begin() as session:
            session.add(row)
            session.flush()
            return _share_out(row, now), token

    def list_shares(self, organization_id: str, scan_id: str) -> list[ShareOut]:
        now = _now()
        with self._session() as session:
            rows = session.scalars(
                select(ReportShareRow)
                .where(ReportShareRow.organization_id == organization_id, ReportShareRow.scan_id == scan_id)
                .order_by(ReportShareRow.created_at.desc())
            ).all()
            return [_share_out(r, now) for r in rows]

    def revoke_share(self, share_id: str, scan_id: str, organization_id: str) -> bool:
        with self._session.begin() as session:
            row = session.get(ReportShareRow, share_id)
            if row is None or row.organization_id != organization_id or row.scan_id != scan_id:
                return False
            if row.revoked_at is None:
                row.revoked_at = _now()
            return True

    def resolve_share(self, token: str) -> tuple[ReportShareRow, ScanRow, str | None] | None:
        """The live share for this secret, or None for anything unknown, revoked or expired."""
        digest = hash_token(token)
        now = _now()
        with self._session() as session:
            share = session.scalar(select(ReportShareRow).where(ReportShareRow.token_hash == digest))
            if share is None or share.revoked_at is not None or _aware(share.expires_at) <= now:
                return None
            scan = session.get(ScanRow, share.scan_id)
            if scan is None or scan.organization_id != share.organization_id:
                return None
            report_id = session.scalar(
                select(ReportRow.id).where(
                    ReportRow.scan_id == share.scan_id, ReportRow.organization_id == share.organization_id
                )
            )
            session.expunge_all()
            return share, scan, report_id

    def record_view(self, share_id: str) -> None:
        with self._session.begin() as session:
            session.execute(
                update(ReportShareRow)
                .where(ReportShareRow.id == share_id)
                .values(view_count=ReportShareRow.view_count + 1, last_viewed_at=_now())
            )
