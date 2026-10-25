"""A schedule that is late, or whose last run failed, is shown as such."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models.schedule import ScanScheduleRow
from app.repositories.schedules import schedule_health
from app.tests.test_schedules import cron_client, target_id_of  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("frequency", "due", "outcome", "expected"),
    [
        ("off", NOW - timedelta(days=5), "error: the run failed", "off"),
        ("daily", NOW + timedelta(hours=5), "completed, score 90", "ok"),
        ("daily", NOW - timedelta(minutes=59), None, "ok"),  # inside the grace period
        ("daily", NOW - timedelta(hours=1, minutes=1), "completed, score 90", "overdue"),
        ("weekly", NOW - timedelta(days=2), "completed, score 90", "overdue"),
        ("daily", NOW + timedelta(hours=5), "error: the run failed", "problem"),
        ("daily", NOW + timedelta(hours=5), "skipped: the monthly scan allowance is used up", "problem"),
        ("daily", NOW + timedelta(hours=5), "failed", "problem"),
        ("daily", NOW + timedelta(hours=5), "started", "ok"),
        ("daily", NOW - timedelta(hours=3), "error: the run failed", "overdue"),  # late is the newer fact
    ],
)
def test_health_rules(frequency: str, due: datetime, outcome: str | None, expected: str) -> None:
    assert schedule_health(frequency, due, outcome, NOW) == expected


def set_state(client: TestClient, **values: object) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.schedules._session.begin() as session:
        session.execute(update(ScanScheduleRow).values(**values))


def test_the_schedule_list_reports_health(cron_client: TestClient) -> None:  # noqa: F811
    tid = target_id_of(cron_client)
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["health"] == "off"
    cron_client.put(
        f"/api/v1/schedules/{tid}", json={"frequency": "daily", "notify": True}
    ).raise_for_status()
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["health"] == "ok"
    set_state(cron_client, next_run_at=datetime.now(UTC) - timedelta(hours=2))
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["health"] == "overdue"
    set_state(
        cron_client, next_run_at=datetime.now(UTC) + timedelta(hours=2), last_outcome="error: the run failed"
    )
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["health"] == "problem"
    cron_client.put(f"/api/v1/schedules/{tid}", json={"frequency": "off", "notify": True}).raise_for_status()
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["health"] == "off"
