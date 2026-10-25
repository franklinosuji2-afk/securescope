"""A schedule is only a reminder to scan: every run is checked again against ownership and the address."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models.schedule import ScanScheduleRow
from app.models.target import TargetRow
from app.tests.conftest import signup, trust_host
from app.tests.test_schedules import SECRET, make_due, run_cron, target_id_of

API = "/api/v1"


@pytest.fixture
def sched(make_settings: Any, mailer: Any, mock_server: str) -> Iterator[tuple[TestClient, str]]:
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0, cron_secret=SECRET)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        tid = target_id_of(client)
        client.put(
            f"{API}/schedules/{tid}",
            json={"frequency": "daily", "notify": False, "url": f"{mock_server}/hardened"},
        ).raise_for_status()
        make_due(client)
        yield client, tid


def scans(client: TestClient) -> int:
    return int(client.get(f"{API}/scans").json()["total"])


def test_a_lapsed_ownership_proof_stops_the_scheduled_scan(sched: Any) -> None:
    client, tid = sched
    state = client.app.state.s
    old = datetime.now(UTC) - timedelta(days=400)
    with state.engine.begin() as conn:
        conn.execute(update(TargetRow).where(TargetRow.id == tid).values(verified_at=old))
    summary = run_cron(client)
    assert summary["scans_started"] == 0 and summary["skipped"] == 1
    assert scans(client) == 0
    assert "no longer verified" in client.get(f"{API}/schedules").json()["items"][0]["last_outcome"]


def test_a_schedule_whose_address_was_changed_to_another_site_does_not_scan_it(sched: Any) -> None:
    client, tid = sched
    state = client.app.state.s
    with state.schedules._session.begin() as session:
        session.execute(
            update(ScanScheduleRow)
            .where(ScanScheduleRow.target_id == tid)
            .values(url="https://victim.example/")
        )
    summary = run_cron(client)
    assert summary["scans_started"] == 0 and summary["skipped"] == 1
    assert scans(client) == 0
    assert "not on the verified site" in client.get(f"{API}/schedules").json()["items"][0]["last_outcome"]


def test_a_site_that_now_points_at_a_private_address_is_not_scanned(
    make_settings: Any,
    mailer: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = [ipaddress.ip_address("93.184.216.34")]

    async def resolve(host: str, port: int) -> list[Any]:
        return list(answers)

    monkeypatch.setattr("app.security.target.resolve_host", resolve)
    settings = make_settings(cron_secret=SECRET)  # private targets stay forbidden
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "rebind.example.com")
        tid = target_id_of(client, "rebind.example.com")
        client.put(
            f"{API}/schedules/{tid}",
            json={"frequency": "daily", "notify": False, "url": "https://rebind.example.com/"},
        ).raise_for_status()
        make_due(client)
        answers[:] = [
            ipaddress.ip_address("169.254.169.254")
        ]  # the name was re-pointed after it was scheduled
        summary = run_cron(client)
        assert summary["scans_started"] == 0 and summary["skipped"] == 1
        assert scans(client) == 0


def test_removing_the_site_removes_its_schedule(sched: Any) -> None:
    client, tid = sched
    assert client.delete(f"{API}/targets/{tid}").status_code == 204
    assert run_cron(client)["due"] == 0
    assert client.get(f"{API}/schedules").json()["items"] == []


def test_a_workspace_that_used_up_its_allowance_is_skipped_not_overrun(sched: Any) -> None:
    client, _ = sched
    state = client.app.state.s

    class Tiny:
        scheduled_scans = True
        scans_per_month = 0

    async def plan(_org: str) -> Tiny:
        return Tiny()

    state.entitlements.plan_for_async = plan
    summary = run_cron(client)
    assert summary["scans_started"] == 0
    assert "allowance" in client.get(f"{API}/schedules").json()["items"][0]["last_outcome"]
