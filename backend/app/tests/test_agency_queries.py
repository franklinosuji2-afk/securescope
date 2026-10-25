"""The agency dashboard asks the database for the newest scan per site; it never loads the whole history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event, update

from app.main import create_app
from app.models.scan import ScanRow
from app.tests.conftest import signup

API = "/api/v1"


def make_scan(client: TestClient, host: str, days_ago: int, status: str = "completed") -> str:
    state = client.app.state.s  # type: ignore[attr-defined]
    me = client.get(f"{API}/auth/me").json()
    scan_id = str(
        state.repo.create_scan(me["organizations"][0]["id"], me["id"], f"https://{host}/", host, None)
    )
    with state.engine.begin() as conn:
        conn.execute(
            update(ScanRow)
            .where(ScanRow.id == scan_id)
            .values(status=status, created_at=datetime.now(UTC) - timedelta(days=days_ago))
        )
    return scan_id


def test_newest_completed_scan_per_host_and_nothing_else(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as alice, TestClient(alice.app) as bob:
        signup(alice, "alice@example.com", "Alice Org")
        signup(bob, "bob@example.com", "Bob Org")
        make_scan(alice, "a.example.com", 9)
        newest = make_scan(alice, "a.example.com", 2)
        make_scan(alice, "a.example.com", 1, status="failed")  # newer, but not a result
        only = make_scan(alice, "b.example.com", 5)
        make_scan(bob, "a.example.com", 0)  # another workspace's scan of the same host name
        state = alice.app.state.s  # type: ignore[attr-defined]
        org = alice.get(f"{API}/auth/me").json()["organizations"][0]["id"]
        found = state.agency.latest_completed_scans(org, ["a.example.com", "b.example.com", "c.example.com"])
    assert found == {"a.example.com": newest, "b.example.com": only}


def test_it_returns_one_row_per_site_however_long_the_history(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as c:
        signup(c, "carol@example.com", "Carol Org")
        for day in range(12):
            make_scan(c, "a.example.com", day + 1)
        state = c.app.state.s  # type: ignore[attr-defined]
        org = c.get(f"{API}/auth/me").json()["organizations"][0]["id"]
        rows_returned: list[int] = []

        def record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]
            rows_returned.append(cursor.rowcount)

        event.listen(state.engine, "after_cursor_execute", record)
        try:
            found = state.agency.latest_completed_scans(org, ["a.example.com"])
        finally:
            event.remove(state.engine, "after_cursor_execute", record)
    assert len(found) == 1
    assert rows_returned == [1]  # one statement, one row, not twelve
