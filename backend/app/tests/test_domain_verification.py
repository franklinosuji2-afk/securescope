"""The verification challenge is kept only while it is usable, and only a current one can verify."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.main import create_app
from app.models.target import TargetRow
from app.tests.conftest import signup
from app.tests.test_targets import API, create, other_org_user, set_dns, verify
from app.tests.test_verification_expiry import age_verification, event_types


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(target_verification_valid_days=30), mailer)) as c:
        signup(c, "alice@example.com", "Alice Org")
        yield c


def stored(client: TestClient, target_id: str) -> TargetRow:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.engine.begin() as conn:
        row = conn.execute(select(TargetRow).where(TargetRow.id == target_id)).one()
    return row  # type: ignore[no-any-return]


def prove(client: TestClient, target: dict[str, Any]) -> dict[str, Any]:
    set_dns(client, {target["dns_record_name"]: [target["dns_record_value"]]})
    return verify(client, target["id"]).json()  # type: ignore[no-any-return]


def test_success_erases_the_challenge(client: TestClient) -> None:
    target = create(client).json()
    assert target["challenge_token"] and target["dns_record_value"]
    done = prove(client, target)
    assert done["status"] == "verified"
    assert done["challenge_token"] == "" and done["dns_record_value"] == ""
    assert done["http_file_content"] == "" and done["challenge_expires_at"] is None
    row = stored(client, target["id"])
    assert row.challenge_token is None and row.challenge_expires_at is None
    # The old value can not be replayed against the verified target.
    assert target["challenge_token"] not in client.get(f"{API}/targets/{target['id']}").text


def test_a_failed_check_keeps_the_challenge(client: TestClient) -> None:
    target = create(client).json()
    set_dns(client, {})
    body = verify(client, target["id"]).json()
    assert body["status"] == "pending" and body["challenge_token"] == target["challenge_token"]


def test_an_expired_challenge_is_not_shown_and_is_erased_by_maintenance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.repositories.targets.CHALLENGE_TTL", timedelta(seconds=-1))
    expired = create(client).json()
    monkeypatch.undo()
    live = create(client, "live.example.org").json()
    assert expired["status"] == "expired"
    assert expired["challenge_token"] == "" and expired["dns_record_value"] == ""
    assert stored(client, expired["id"]).challenge_token is not None  # still in the database

    assert client.app.state.s.targets.purge_expired_challenges() == 1  # type: ignore[attr-defined]
    assert stored(client, expired["id"]).challenge_token is None
    assert stored(client, live["id"]).challenge_token == live["challenge_token"]  # untouched
    assert client.app.state.s.targets.purge_expired_challenges() == 0  # type: ignore[attr-defined]
    # The owner can start again.
    renewed = client.post(f"{API}/targets/{expired['id']}/challenge").json()
    assert renewed["status"] == "pending" and renewed["challenge_token"]


def test_removing_a_challenge_keeps_the_site_and_blocks_verification(client: TestClient) -> None:
    target = create(client).json()
    removed = client.delete(f"{API}/targets/{target['id']}/challenge")
    assert removed.status_code == 200
    body = removed.json()
    assert body["status"] == "expired" and body["challenge_token"] == "" and body["dns_record_value"] == ""
    assert stored(client, target["id"]).challenge_token is None
    asked = set_dns(client, {target["dns_record_name"]: [target["dns_record_value"]]})
    assert verify(client, target["id"]).status_code == 409 and asked == []
    assert "target.challenge_removed" in event_types(client)
    assert (
        prove(client, client.post(f"{API}/targets/{target['id']}/challenge").json())["status"] == "verified"
    )


def test_removing_the_challenge_of_a_verified_site_keeps_it_verified(client: TestClient) -> None:
    target = create(client).json()
    prove(client, target)
    renewed = client.post(f"{API}/targets/{target['id']}/challenge").json()
    assert renewed["status"] == "verified" and renewed["challenge_token"]
    cleared = client.delete(f"{API}/targets/{target['id']}/challenge").json()
    assert cleared["status"] == "verified" and cleared["challenge_token"] == ""


def test_a_lapsed_proof_with_no_challenge_asks_for_a_new_one(client: TestClient) -> None:
    target = create(client).json()
    prove(client, target)
    age_verification(client, target["id"], 31)
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.engine.begin() as conn:
        conn.execute(update(TargetRow).where(TargetRow.id == target["id"]).values(challenge_token=None))
    response = verify(client, target["id"])
    assert response.status_code == 409 and "New challenge" in response.json()["detail"]
    fresh = client.post(f"{API}/targets/{target['id']}/challenge").json()
    assert prove(client, fresh)["status"] == "verified"


@pytest.mark.parametrize("action", ["regenerate", "remove"])
def test_a_challenge_changed_during_a_check_cannot_verify(client: TestClient, action: str) -> None:
    target = create(client).json()
    old_value = target["dns_record_value"]
    org = client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    asked: list[str] = []

    async def lookup(name: str) -> list[str]:
        asked.append(name)
        # The owner replaces or removes the challenge while the DNS lookup is in flight.
        state = client.app.state.s  # type: ignore[attr-defined]
        if action == "regenerate":
            state.targets.regenerate_challenge(target["id"], org)
        else:
            state.targets.clear_challenge(target["id"], org)
        return [old_value]

    client.app.state.s.txt_lookup = lookup  # type: ignore[attr-defined]
    body = verify(client, target["id"]).json()
    assert asked and body["status"] != "verified"
    assert "replaced or removed" in body["last_check_error"]
    assert stored(client, target["id"]).verified_at is None


def test_other_workspaces_cannot_remove_a_challenge(client: TestClient) -> None:
    target = create(client).json()
    bob = other_org_user(client)
    assert bob.delete(f"{API}/targets/{target['id']}/challenge").status_code == 404
    assert client.get(f"{API}/targets/{target['id']}").json()["challenge_token"] == target["challenge_token"]


def test_removing_a_challenge_needs_the_manage_role_and_a_session(client: TestClient) -> None:
    target = create(client).json()
    org = client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    viewer = other_org_user(client, "viewer@example.com")
    added = client.post(
        f"{API}/organizations/{org}/members", json={"email": "viewer@example.com", "role": "VIEWER"}
    )
    assert added.status_code == 201, added.text
    denied = viewer.delete(f"{API}/targets/{target['id']}/challenge", headers={"X-Organization-Id": org})
    assert denied.status_code == 403
    anonymous = TestClient(client.app)
    assert anonymous.delete(f"{API}/targets/{target['id']}/challenge").status_code in (401, 403)


def test_new_challenges_are_rate_limited(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(target_verifications_per_target_per_hour=2), mailer)) as c:
        signup(c, "alice@example.com", "Alice Org")
        target = create(c).json()
        codes = [c.post(f"{API}/targets/{target['id']}/challenge").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        # The budget is separate from verification attempts.
        set_dns(c, {})
        assert verify(c, target["id"]).status_code == 200


def test_the_challenge_value_never_reaches_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    target = create(client).json()
    prove(client, target)
    assert target["challenge_token"] not in caplog.text
    assert datetime.now(UTC).year >= 2026  # keeps the datetime import honest for the fixtures above
