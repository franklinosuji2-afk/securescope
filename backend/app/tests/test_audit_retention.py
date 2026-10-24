"""Audit-log retention: entries older than the period are deleted, newer ones stay, and the period is shown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.main import create_app
from app.models.account import AuditEventRow
from app.tests.conftest import signup

API = "/api/v1"


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(audit_retention_days=365), mailer)) as c:
        signup(c, "alice@example.com", "Alice Org")
        yield c


def _count(client: TestClient) -> int:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(AuditEventRow)).scalar() or 0)


def _age_all(client: TestClient, days: int, only_type: str | None = None) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    stmt = update(AuditEventRow).values(timestamp=datetime.now(UTC) - timedelta(days=days))
    if only_type:
        stmt = stmt.where(AuditEventRow.event_type == only_type)
    with state.engine.begin() as conn:
        conn.execute(stmt)


def test_only_entries_past_the_retention_period_are_deleted(client: TestClient) -> None:
    audit = client.app.state.s.audit  # type: ignore[attr-defined]
    total = _count(client)
    assert total >= 1  # registering recorded something
    assert audit.delete_older_than(365) == 0
    _age_all(client, 364)
    assert audit.delete_older_than(365) == 0 and _count(client) == total
    _age_all(client, 366)
    assert audit.delete_older_than(365) == total
    assert _count(client) == 0


def test_a_new_entry_survives_while_old_ones_go(client: TestClient) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    _age_all(client, 400)
    state.audit.record("test.recent")
    assert state.audit.delete_older_than(365) >= 1
    with state.engine.connect() as conn:
        left = conn.execute(select(AuditEventRow.event_type)).scalars().all()
    assert left == ["test.recent"]


def test_entries_of_a_deleted_workspace_are_also_removed_when_old(client: TestClient) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.engine.begin() as conn:
        conn.execute(
            update(AuditEventRow).values(
                organization_id=None, timestamp=datetime.now(UTC) - timedelta(days=500)
            )
        )
    assert state.audit.delete_older_than(365) >= 1


def test_the_audit_page_reports_the_retention_period(client: TestClient) -> None:
    body = client.get(f"{API}/audit-events").json()
    assert body["retention_days"] == 365


def test_the_period_is_bounded(make_settings) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        make_settings(audit_retention_days=1)
    with pytest.raises(ValueError):
        make_settings(audit_retention_days=100000)
    assert make_settings().audit_retention_days == 365


def test_the_hourly_maintenance_pass_applies_the_retention_period(client: TestClient) -> None:
    import asyncio

    from app.main import _maintenance_loop

    state = client.app.state.s  # type: ignore[attr-defined]
    _age_all(client, 500)
    assert _count(client) >= 1

    async def one_pass() -> None:
        try:
            await asyncio.wait_for(_maintenance_loop(state), timeout=3)
        except TimeoutError:
            pass  # the loop sleeps for an hour after its first pass; stop it there

    asyncio.run(one_pass())
    assert _count(client) == 0
