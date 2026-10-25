"""The activation funnel is counted from existing rows, for the operator only, and carries no identifiers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models.account import OrganizationRow
from app.models.scan import ScanRow
from app.tests.conftest import signup

ADMIN = "boss@example.com"
API = "/api/v1"


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(admin_email=ADMIN, analytics_salt="s" * 32)
    with TestClient(create_app(settings, mailer)) as c:
        yield c


def admin_of(client: TestClient, mailer) -> TestClient:  # type: ignore[no-untyped-def]
    admin = TestClient(client.app)
    signup(admin, ADMIN, "Boss Org")
    token = next(body for to, _s, body in mailer.sent if to == ADMIN).rsplit("token=", 1)[1].strip()
    assert admin.post(f"{API}/auth/verify-email", json={"token": token}).status_code in (200, 204)
    return admin


def org_of(c: TestClient) -> str:
    return str(c.get(f"{API}/auth/me").json()["organizations"][0]["id"])


def complete_scan(
    c: TestClient, minutes_after_signup: int, host: str = "a.example.com", status: str = "completed"
) -> None:
    state = c.app.state.s  # type: ignore[attr-defined]
    user = c.get(f"{API}/auth/me").json()["id"]
    org = org_of(c)
    scan_id = state.repo.create_scan(org, user, f"https://{host}/", host, None)
    with state.engine.begin() as conn:
        made = (
            conn.execute(OrganizationRow.__table__.select().where(OrganizationRow.id == org)).one().created_at
        )
        if made.tzinfo is None:
            made = made.replace(tzinfo=UTC)
        conn.execute(
            update(ScanRow)
            .where(ScanRow.id == scan_id)
            .values(status=status, finished_at=made + timedelta(minutes=minutes_after_signup))
        )


def funnel(admin: TestClient, days: int = 30) -> dict[str, object]:
    response = admin.get(f"{API}/analytics/activation?days={days}")
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_only_the_operator_can_read_the_funnel(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    assert client.get(f"{API}/analytics/activation").status_code == 401
    with TestClient(client.app) as other:
        signup(other, "someone@example.com", "Other Org")
        assert other.get(f"{API}/analytics/activation").status_code == 404
    admin = admin_of(client, mailer)
    assert admin.get(f"{API}/analytics/activation").status_code == 200


def test_parameters_are_validated(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = admin_of(client, mailer)
    assert admin.get(f"{API}/analytics/activation?days=0").status_code == 422
    assert admin.get(f"{API}/analytics/activation?days=400").status_code == 422


def test_an_empty_period_shows_zeros_not_invented_numbers(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = admin_of(client, mailer)
    data = funnel(admin)
    assert data["created"] == 1  # the operator's own workspace is the only one
    for step in (
        "website_added",
        "website_verified",
        "first_scan_completed",
        "second_scan_completed",
        "monitoring_enabled",
        "report_downloaded",
        "api_token_created",
    ):
        assert data[step] == 0
    assert data["median_seconds_to_first_scan"] is None
    assert data["small_cohort"] is True


def test_each_step_is_counted_once_per_workspace(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = admin_of(client, mailer)
    with TestClient(client.app) as a, TestClient(client.app) as b:
        signup(a, "a@example.com", "A Org")
        signup(b, "b@example.com", "B Org")
        from app.tests.conftest import trust_host

        trust_host(a, "a.example.com")
        trust_host(a, "a2.example.com")  # two sites in one workspace still count once
        b.post(f"{API}/targets", json={"hostname": "b.example.com"}, headers={"X-Organization-Id": org_of(b)})
        complete_scan(a, 12)
        complete_scan(a, 30)
        complete_scan(b, 3, host="b.example.com")
        complete_scan(b, 1, host="b.example.com", status="failed")  # a failed scan is not a first scan
        state = client.app.state.s  # type: ignore[attr-defined]
        state.audit.record("report.downloaded", organization_id=org_of(a), resource_type="scan")
        state.audit.record("report.downloaded", organization_id=org_of(a), resource_type="scan")
        data = funnel(admin)
    assert data["created"] == 3
    assert data["website_added"] == 2
    assert data["website_verified"] == 1
    assert data["first_scan_completed"] == 2
    assert data["second_scan_completed"] == 1
    assert data["report_downloaded"] == 1
    # Median of 12 and 3 minutes after sign-up.
    assert data["median_seconds_to_first_scan"] == int(7.5 * 60)
    assert data["small_cohort"] is True


def test_older_workspaces_and_unfinished_scans_are_left_out(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = admin_of(client, mailer)
    with TestClient(client.app) as old:
        signup(old, "old@example.com", "Old Org")
        state = client.app.state.s  # type: ignore[attr-defined]
        user = old.get(f"{API}/auth/me").json()["id"]
        state.repo.create_scan(org_of(old), user, "https://o.example.com/", "o.example.com", None)  # queued
        with state.engine.begin() as conn:
            conn.execute(
                update(OrganizationRow)
                .where(OrganizationRow.id == org_of(old))
                .values(created_at=datetime.now(UTC) - timedelta(days=60))
            )
        assert funnel(admin, days=30)["created"] == 1
        wide = funnel(admin, days=90)
    assert wide["created"] == 2
    assert wide["first_scan_completed"] == 0  # a queued scan is not a completed one


def test_the_answer_carries_no_identifiers(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = admin_of(client, mailer)
    with TestClient(client.app) as a:
        signup(a, "visible@example.com", "Visible Org")
        from app.tests.conftest import trust_host

        trust_host(a, "private-site.example.com")
        raw = admin.get(f"{API}/analytics/activation").text
    for secret in ("visible@example.com", "Visible Org", "private-site", org_of(admin)):
        assert secret not in raw
    keys = set(admin.get(f"{API}/analytics/activation").json())
    assert keys == {
        "range_days",
        "created",
        "website_added",
        "website_verified",
        "first_scan_completed",
        "second_scan_completed",
        "monitoring_enabled",
        "report_downloaded",
        "api_token_created",
        "median_seconds_to_first_scan",
        "small_cohort",
    }
