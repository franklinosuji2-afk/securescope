"""Plans and limits: what each plan includes is enforced by the server, per organization, never by the browser."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.billing.errors import PlanLimitError
from app.billing.plans import AGENCY, FREE, INTERNAL, PLANS, PROFESSIONAL, current_period, get_plan
from app.core.config import Settings
from app.main import create_app
from app.models.scan import FindingRow, ReportRow, ScanRow
from app.tests.conftest import CapturingMailer, signup, trust_host

API = "/api/v1"


@pytest.fixture
def free_app(make_settings, mailer):  # type: ignore[no-untyped-def]
    """The real default: workspaces without an assigned plan are on Free."""
    settings = make_settings(
        default_plan=None,
        allow_private_targets=True,
        request_timeout_seconds=1.0,
        scans_per_target_per_hour=50,
    )
    with TestClient(create_app(settings, mailer)) as client:
        yield client


@pytest.fixture
def alice(free_app: TestClient) -> TestClient:
    signup(free_app, "alice@example.com", "Alice Org")
    return free_app


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def state_of(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.s  # type: ignore[attr-defined]


def add_site(client: TestClient, host: str):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/targets", json={"hostname": host})


# --- the catalogue ----------------------------------------------------------------------------------


def test_the_catalogue_matches_the_published_plans() -> None:
    assert [(p.id, p.price_eur_month) for p in (FREE, PROFESSIONAL, AGENCY)] == [
        ("free", 0),
        ("professional", 19),
        ("agency", 49),
    ]
    assert (FREE.max_websites, PROFESSIONAL.max_websites, AGENCY.max_websites) == (1, 5, 20)
    assert (FREE.scans_per_month, PROFESSIONAL.scans_per_month, AGENCY.scans_per_month) == (3, 30, 150)
    assert (FREE.history_days, PROFESSIONAL.history_days, AGENCY.history_days) == (30, 90, 365)
    assert [p.can_invite for p in (FREE, PROFESSIONAL, AGENCY)] == [False, False, True]
    assert [p.client_workspace for p in (FREE, PROFESSIONAL, AGENCY, INTERNAL)] == [False, False, True, True]
    assert [p.scheduled_scans for p in (FREE, PROFESSIONAL, AGENCY, INTERNAL)] == [False, True, True, True]


def test_only_the_internal_plan_is_unlimited_and_it_cannot_be_bought() -> None:
    assert INTERNAL.max_websites is None and INTERNAL.scans_per_month is None
    assert not INTERNAL.purchasable and not FREE.purchasable
    assert all(
        p.max_websites is not None and p.scans_per_month is not None for p in (FREE, PROFESSIONAL, AGENCY)
    )


def test_an_unknown_or_missing_plan_falls_back_to_free() -> None:
    assert get_plan(None) is FREE
    assert get_plan("platinum-forever") is FREE
    assert set(PLANS) == {"free", "professional", "agency", "internal"}


def test_the_monthly_period_is_the_calendar_month_in_utc() -> None:
    start, end = current_period(datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
    assert (start, end) == (datetime(2026, 12, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    start, end = current_period(datetime(2026, 2, 10, 5, 0, tzinfo=UTC))
    assert (start, end) == (datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC))


# --- websites ---------------------------------------------------------------------------------------


def test_a_free_workspace_can_register_one_website_and_not_a_second(alice: TestClient) -> None:
    assert add_site(alice, "first.example.com").status_code == 201
    second = add_site(alice, "second.example.com")
    assert second.status_code == 403
    assert "1 website" in second.json()["detail"]


def test_removing_a_website_frees_the_slot(alice: TestClient) -> None:
    first = add_site(alice, "first.example.com").json()
    assert alice.delete(f"{API}/targets/{first['id']}").status_code == 204
    assert add_site(alice, "second.example.com").status_code == 201


def test_a_paid_plan_raises_the_website_limit_and_stops_at_its_own(alice: TestClient) -> None:
    state_of(alice).plans.set_plan(org_of(alice), "professional", "system")
    for number in range(5):
        assert add_site(alice, f"site{number}.example.com").status_code == 201
    assert add_site(alice, "site5.example.com").status_code == 403


def test_simultaneous_requests_cannot_take_more_websites_than_the_plan_allows(alice: TestClient) -> None:
    state = state_of(alice)
    org = org_of(alice)
    user = alice.get(f"{API}/auth/me").json()["id"]
    results: list[str] = []

    def attempt(number: int) -> None:
        try:
            state.targets.create(org, f"race{number}.example.com", user, 2)
            results.append("created")
        except PlanLimitError:
            results.append("refused")

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("created") == 2 and results.count("refused") == 8


def test_one_workspaces_usage_never_counts_against_another(free_app: TestClient) -> None:
    signup(free_app, "alice@example.com", "Alice Org")
    assert add_site(free_app, "alice.example.com").status_code == 201
    other = TestClient(free_app.app)
    signup(other, "bob@example.com", "Bob Org")
    assert add_site(other, "bob.example.com").status_code == 201


# --- scans ------------------------------------------------------------------------------------------


def start_scan(client: TestClient, mock_server: str):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/scans", json={"url": f"{mock_server}/plain", "authorization_confirmed": True})


def test_a_free_workspace_gets_three_scans_a_month_and_the_fourth_is_refused(
    alice: TestClient, mock_server: str
) -> None:
    trust_host(alice, "127.0.0.1")
    for _ in range(3):
        assert start_scan(alice, mock_server).status_code == 202
    fourth = start_scan(alice, mock_server)
    assert fourth.status_code == 403
    assert "3 scans per month" in fourth.json()["detail"]


def test_scans_that_failed_do_not_use_up_the_allowance(alice: TestClient) -> None:
    state = state_of(alice)
    org = org_of(alice)
    user = alice.get(f"{API}/auth/me").json()["id"]
    start, _ = current_period(datetime.now(UTC))
    for _ in range(3):
        state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None, 3, start)
    with pytest.raises(PlanLimitError):
        state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None, 3, start)
    assert state.repo.fail_interrupted() == 3  # the three queued scans are marked failed
    state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None, 3, start)


def test_last_months_scans_do_not_count_this_month(alice: TestClient) -> None:
    state = state_of(alice)
    org = org_of(alice)
    user = alice.get(f"{API}/auth/me").json()["id"]
    start, _ = current_period(datetime.now(UTC))
    for _ in range(3):
        scan_id = state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None)
        with state.engine.begin() as conn:
            conn.execute(
                update(ScanRow).where(ScanRow.id == scan_id).values(created_at=start - timedelta(days=1))
            )
    state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None, 3, start)


def test_simultaneous_scan_requests_cannot_exceed_the_monthly_allowance(alice: TestClient) -> None:
    state = state_of(alice)
    org = org_of(alice)
    user = alice.get(f"{API}/auth/me").json()["id"]
    start, _ = current_period(datetime.now(UTC))
    results: list[str] = []

    def attempt() -> None:
        try:
            state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None, 3, start)
            results.append("created")
        except PlanLimitError:
            results.append("refused")

    threads = [threading.Thread(target=attempt) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("created") == 3 and results.count("refused") == 9


def test_the_internal_plan_has_no_scan_or_website_limit(free_app: TestClient, mock_server: str) -> None:
    signup(free_app, "alice@example.com", "Alice Org")
    state_of(free_app).plans.set_plan(org_of(free_app), "internal", "system")
    trust_host(free_app, "127.0.0.1")
    for number in range(4):
        assert add_site(free_app, f"many{number}.example.com").status_code == 201
    for _ in range(4):
        assert start_scan(free_app, mock_server).status_code == 202


# --- the plan view ----------------------------------------------------------------------------------


def test_an_owner_sees_the_plan_limits_and_usage(alice: TestClient) -> None:
    assert add_site(alice, "first.example.com").status_code == 201
    body = alice.get(f"{API}/organizations/{org_of(alice)}/plan").json()
    assert body["plan_id"] == "free" and body["price_eur_month"] == 0
    assert body["limits"] == {
        "websites": 1,
        "scans_per_month": 3,
        "history_days": 30,
        "can_invite": False,
        "client_workspace": False,
        "scheduled_scans": False,
    }
    assert body["usage"]["websites"] == 1 and body["usage"]["scans_this_period"] == 0


def test_a_client_cannot_see_billing_and_nobody_sees_another_workspaces_plan(free_app: TestClient) -> None:
    signup(free_app, "alice@example.com", "Alice Org")
    alice_org = org_of(free_app)
    state_of(free_app).plans.set_plan(alice_org, "agency", "system")
    bob = TestClient(free_app.app)
    signup(bob, "bob@example.com", "Bob Org")
    assert bob.get(f"{API}/organizations/{alice_org}/plan").status_code in (403, 404)
    assert bob.get(f"{API}/organizations/{org_of(bob)}/plan").status_code == 200


# --- team features ----------------------------------------------------------------------------------


def test_inviting_and_adding_people_needs_the_agency_plan(alice: TestClient) -> None:
    org = org_of(alice)
    refused = alice.post(
        f"{API}/organizations/{org}/invitations", json={"email": "c@example.com", "role": "VIEWER"}
    )
    assert refused.status_code == 403 and "Agency" in refused.json()["detail"]
    other = TestClient(alice.app)
    signup(other, "bob@example.com", "Bob Org")
    added = alice.post(
        f"{API}/organizations/{org}/members", json={"email": "bob@example.com", "role": "VIEWER"}
    )
    assert added.status_code == 403
    state_of(alice).plans.set_plan(org, "agency", "system")
    allowed = alice.post(
        f"{API}/organizations/{org}/invitations", json={"email": "c@example.com", "role": "VIEWER"}
    )
    assert allowed.status_code == 201, allowed.text


def test_professional_cannot_invite(alice: TestClient) -> None:
    org = org_of(alice)
    state_of(alice).plans.set_plan(org, "professional", "system")
    response = alice.post(
        f"{API}/organizations/{org}/invitations", json={"email": "c@example.com", "role": "VIEWER"}
    )
    assert response.status_code == 403


# --- history ----------------------------------------------------------------------------------------


def age(client: TestClient, org: str, days: int) -> str:
    state = state_of(client)
    user = client.get(f"{API}/auth/me").json()["id"]
    scan_id = state.repo.create_scan(org, user, "https://a.example.com/", "a.example.com", None)
    with state.engine.begin() as conn:
        conn.execute(
            update(ScanRow)
            .where(ScanRow.id == scan_id)
            .values(created_at=datetime.now(UTC) - timedelta(days=days))
        )
    return str(scan_id)


def exists(client: TestClient, scan_id: str) -> bool:
    with state_of(client).engine.connect() as conn:
        return conn.execute(select(ScanRow.id).where(ScanRow.id == scan_id)).first() is not None


def test_each_plan_keeps_scan_history_for_its_own_window(free_app: TestClient) -> None:
    signup(free_app, "alice@example.com", "Alice Org")
    free_org = org_of(free_app)
    pro = TestClient(free_app.app)
    signup(pro, "pro@example.com", "Pro Org")
    pro_org = org_of(pro)
    agency = TestClient(free_app.app)
    signup(agency, "agency@example.com", "Agency Org")
    agency_org = org_of(agency)
    plans = state_of(free_app).plans
    plans.set_plan(pro_org, "professional", "system")
    plans.set_plan(agency_org, "agency", "system")

    kept_free, gone_free = age(free_app, free_org, 29), age(free_app, free_org, 31)
    kept_pro, gone_pro = age(pro, pro_org, 89), age(pro, pro_org, 91)
    kept_agency, gone_agency = age(agency, agency_org, 364), age(agency, agency_org, 366)

    assert state_of(free_app).repo.delete_expired_history() == 3
    assert [exists(free_app, s) for s in (kept_free, kept_pro, kept_agency)] == [True, True, True]
    assert [exists(free_app, s) for s in (gone_free, gone_pro, gone_agency)] == [False, False, False]


def test_deleting_old_history_removes_its_findings_and_reports_too(free_app: TestClient) -> None:
    signup(free_app, "alice@example.com", "Alice Org")
    scan_id = age(free_app, org_of(free_app), 40)
    state_of(free_app).repo.delete_expired_history()
    with state_of(free_app).engine.connect() as conn:
        assert conn.execute(select(FindingRow.row_id).where(FindingRow.scan_id == scan_id)).first() is None
        assert conn.execute(select(ReportRow.scan_id).where(ReportRow.scan_id == scan_id)).first() is None


def test_a_downgrade_keeps_existing_websites_and_only_blocks_new_ones(alice: TestClient) -> None:
    org = org_of(alice)
    state_of(alice).plans.set_plan(org, "professional", "system")
    for number in range(3):
        assert add_site(alice, f"site{number}.example.com").status_code == 201
    state_of(alice).plans.set_plan(org, "free", "system")
    assert len(alice.get(f"{API}/targets").json()["items"]) == 3
    assert add_site(alice, "another.example.com").status_code == 403


# --- the operator's own workspaces ------------------------------------------------------------------


def test_the_operators_workspaces_are_put_on_the_internal_plan(
    make_settings: Callable[..., Settings], mailer: CapturingMailer
) -> None:
    settings = make_settings(default_plan=None, admin_email="owner@example.com")
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "owner@example.com", "Owner Org")
        other = TestClient(client.app)
        signup(other, "customer@example.com", "Customer Org")
        plans = state_of(client).plans
        assert plans.assign_internal_to_operator("OWNER@example.com") == 1
        assert plans.plan_id(org_of(client)) == "internal"
        assert plans.plan_id(org_of(other)) is None
        assert plans.assign_internal_to_operator("owner@example.com") == 0  # nothing changes the second time
