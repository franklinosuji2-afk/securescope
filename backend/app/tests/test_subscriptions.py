"""Subscription groundwork: which plan applies, repeated provider events, and the read-only downgrade preview.

No billing provider is connected. These tests write subscription rows directly, the way a verified provider
event will later, to prove the rules before real money depends on them."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.billing.lifecycle import SubscriptionState, effective_plan_id
from app.main import create_app
from app.tests.conftest import signup

API = "/api/v1"
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=10)
EARLIER = NOW - timedelta(days=1)


def sub(plan: str = "professional", status: str = "active", end=LATER, cancel=False, pending=None):  # type: ignore[no-untyped-def]
    return SubscriptionState("test", plan, status, end, cancel, pending)


# The rule itself ------------------------------------------------------------------------------------------


def test_no_subscription_changes_nothing() -> None:
    assert effective_plan_id(None, None, NOW) is None
    assert effective_plan_id("agency", None, NOW) == "agency"


def test_an_active_subscription_gives_its_plan() -> None:
    assert effective_plan_id(None, sub("agency"), NOW) == "agency"


def test_a_cancelled_subscription_keeps_paid_access_until_the_period_ends_and_not_after() -> None:
    cancelled = sub(status="canceled", cancel=True)
    assert effective_plan_id(None, cancelled, NOW) == "professional"
    assert effective_plan_id(None, cancelled, LATER) is None
    assert effective_plan_id(None, cancelled, LATER + timedelta(seconds=1)) is None


def test_a_subscription_set_to_end_stays_until_the_end_date() -> None:
    ending = sub(cancel=True)
    assert effective_plan_id(None, ending, NOW) == "professional"
    assert effective_plan_id(None, ending, LATER + timedelta(days=1)) is None


def test_past_due_keeps_the_plan_only_until_the_period_ends() -> None:
    late = sub(status="past_due")
    assert effective_plan_id(None, late, NOW) == "professional"
    assert effective_plan_id(None, late, LATER) is None


def test_a_requested_downgrade_starts_when_the_period_ends() -> None:
    down = sub("agency", pending="professional")
    assert effective_plan_id(None, down, NOW) == "agency"
    assert effective_plan_id(None, down, LATER) == "professional"
    # A cancelled subscription does not start a pending plan.
    assert effective_plan_id(None, sub("agency", "canceled", pending="professional"), LATER) is None


def test_the_end_of_a_subscription_returns_to_the_plan_the_workspace_had_before() -> None:
    assert effective_plan_id("agency", sub(end=EARLIER), NOW) == "agency"
    assert effective_plan_id(None, sub(end=EARLIER), NOW) is None


def test_the_internal_plan_is_never_changed_by_a_subscription() -> None:
    assert effective_plan_id("internal", sub(end=EARLIER), NOW) == "internal"
    assert effective_plan_id("internal", sub("agency"), NOW) == "internal"


@pytest.mark.parametrize("plan", ["internal", "free", "nonsense"])
def test_a_subscription_cannot_grant_a_plan_nobody_can_buy(plan: str) -> None:
    assert effective_plan_id(None, sub(plan), NOW) is None


def test_a_subscription_without_an_end_date_counts_only_while_active_and_not_ending() -> None:
    assert effective_plan_id(None, sub(end=None), NOW) == "professional"
    assert effective_plan_id(None, sub(end=None, cancel=True), NOW) is None
    assert effective_plan_id(None, sub(status="canceled", end=None), NOW) is None
    assert effective_plan_id(None, sub(status="unknown"), NOW) is None


def test_naive_database_datetimes_are_read_as_utc() -> None:
    naive_end = (NOW + timedelta(days=1)).replace(tzinfo=None)
    assert effective_plan_id(None, sub(end=naive_end), NOW) == "professional"


# Through the app ------------------------------------------------------------------------------------------


@pytest.fixture
def app(make_settings, mailer):  # type: ignore[no-untyped-def]
    return create_app(make_settings(default_plan=None, allow_private_targets=True), mailer)


@pytest.fixture
def alice(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as client:
        signup(client, "alice@example.com", "Alice Org")
        yield client


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def state_of(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.s  # type: ignore[attr-defined]


def plan_of(client: TestClient) -> dict:  # type: ignore[type-arg]
    return client.get(f"{API}/organizations/{org_of(client)}/plan").json()  # type: ignore[no-any-return]


def test_existing_workspaces_are_unchanged_without_a_subscription(alice: TestClient) -> None:
    body = plan_of(alice)
    assert body["plan_id"] == "free"
    assert body["subscription"] is None


def test_a_stored_subscription_changes_the_plan_and_is_reported(alice: TestClient) -> None:
    state = state_of(alice)
    state.billing.save_subscription(org_of(alice), "sub_1", sub("professional"))
    body = plan_of(alice)
    assert body["plan_id"] == "professional"
    assert body["limits"]["websites"] == 5
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["cancel_at_period_end"] is False


def test_an_ended_subscription_returns_the_workspace_to_free_and_keeps_its_data(alice: TestClient) -> None:
    org = org_of(alice)
    state = state_of(alice)
    state.billing.save_subscription(org, "sub_1", sub("professional"))
    assert alice.post(f"{API}/targets", json={"hostname": "one.example.com"}).status_code == 201
    assert alice.post(f"{API}/targets", json={"hostname": "two.example.com"}).status_code == 201
    state.billing.save_subscription(org, "sub_1", sub("professional", "canceled", end=EARLIER))
    assert plan_of(alice)["plan_id"] == "free"
    sites = alice.get(f"{API}/targets").json()
    assert len(sites["items"] if isinstance(sites, dict) else sites) == 2
    # Over the Free limit: nothing deleted, but no third site.
    assert alice.post(f"{API}/targets", json={"hostname": "three.example.com"}).status_code == 403


def test_the_same_provider_event_is_applied_once(alice: TestClient) -> None:
    repo = state_of(alice).billing
    org = org_of(alice)
    assert repo.record_event("test", "evt_1", "subscription.created", org) is True
    assert repo.record_event("test", "evt_1", "subscription.created", org) is False
    assert repo.record_event("other", "evt_1", "subscription.created", org) is True
    assert repo.record_event("test", "evt_2", "subscription.updated", None) is True


def test_a_subscription_is_removed_with_the_workspace_and_events_are_kept_without_it(
    alice: TestClient,
) -> None:
    org = org_of(alice)
    repo = state_of(alice).billing
    repo.save_subscription(org, "sub_1", sub("professional"))
    assert repo.record_event("test", "evt_9", "subscription.created", org) is True
    from app.tests.conftest import PASSWORD

    response = alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
    assert response.status_code == 204, response.text
    assert repo.subscription(org) is None
    # The event id stays recorded (so a late repeat is still ignored); it no longer points at a workspace.
    assert repo.record_event("test", "evt_9", "subscription.created", None) is False


# The downgrade preview ------------------------------------------------------------------------------------


def preview(client: TestClient, to: str, org: str | None = None):  # type: ignore[no-untyped-def]
    return client.get(
        f"{API}/organizations/{org or org_of(client)}/plan/downgrade-preview", params={"to": to}
    )


def test_the_preview_lists_what_would_exceed_a_lower_plan_and_changes_nothing(alice: TestClient) -> None:
    org = org_of(alice)
    state = state_of(alice)
    state.plans.set_plan(org, "agency", "system")
    for host in ("a.example.com", "b.example.com", "c.example.com"):
        assert alice.post(f"{API}/targets", json={"hostname": host}).status_code == 201
    before = plan_of(alice)
    response = preview(alice, "free")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_plan_id"] == "agency"
    assert body["target_plan_id"] == "free"
    assert body["deletes_nothing_now"] is True
    effects = {e["key"]: e for e in body["effects"]}
    assert effects["websites"]["used"] == 3 and effects["websites"]["limit"] == 1
    assert effects["websites"]["kind"] == "over_limit"
    assert {"scheduled_scans", "team", "clients"} <= set(effects)
    assert effects["clients"]["kind"] == "feature_lost"
    # Reading changed nothing: same plan, same sites.
    assert plan_of(alice) == before
    assert len(alice.get(f"{API}/targets").json()["items"]) == 3


def test_the_preview_is_empty_when_nothing_would_exceed(alice: TestClient) -> None:
    state_of(alice).plans.set_plan(org_of(alice), "professional", "system")
    assert preview(alice, "free").json()["effects"][0]["key"] == "scheduled_scans"
    state_of(alice).plans.set_plan(org_of(alice), "free", "system")
    assert preview(alice, "free").json()["effects"] == []


def test_the_preview_rejects_unknown_and_internal_plans(alice: TestClient) -> None:
    assert preview(alice, "internal").status_code == 404
    assert preview(alice, "gold").status_code == 404
    assert alice.get(f"{API}/organizations/{org_of(alice)}/plan/downgrade-preview").status_code == 422


def test_nobody_previews_another_workspaces_downgrade(alice: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    alice_org = org_of(alice)
    with TestClient(app) as bob:
        signup(bob, "bob@example.com", "Bob Org")
        assert preview(bob, "free", alice_org).status_code in (403, 404)
        assert preview(bob, "free").status_code == 200
    with TestClient(app) as anonymous:
        assert preview(anonymous, "free", alice_org).status_code == 401
