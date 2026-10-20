"""Ownership proofs expire and can be renewed only with a fresh challenge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models.target import TargetRow
from app.tests.conftest import signup
from app.tests.test_targets import API, create, set_dns, verify


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(target_verification_valid_days=30), mailer)) as c:
        signup(c, "alice@example.com", "Alice Org")
        yield c


def prove(client: TestClient, target: dict[str, Any]) -> dict[str, Any]:
    set_dns(client, {target["dns_record_name"]: [target["dns_record_value"]]})
    return verify(client, target["id"]).json()  # type: ignore[no-any-return]


def age_verification(client: TestClient, target_id: str, days: int) -> None:
    """Moves the proof `days` into the past. Its challenge was issued just before it was proven."""
    state = client.app.state.s  # type: ignore[attr-defined]
    proven = datetime.now(UTC) - timedelta(days=days)
    with state.engine.begin() as conn:
        conn.execute(
            update(TargetRow)
            .where(TargetRow.id == target_id)
            .values(verified_at=proven, challenge_expires_at=proven + timedelta(days=6))
        )


def event_types(client: TestClient) -> list[str]:
    return [e["event_type"] for e in client.get(f"{API}/audit-events?limit=100").json()["items"]]


def test_a_fresh_proof_shows_when_it_will_lapse(client: TestClient) -> None:
    done = prove(client, create(client).json())
    assert done["status"] == "verified"
    verified = datetime.fromisoformat(done["verified_at"])
    lapses = datetime.fromisoformat(done["verification_expires_at"])
    assert lapses - verified == timedelta(days=30)


def test_a_lapsed_proof_blocks_scans_with_a_clear_reason(client: TestClient) -> None:
    target = create(client).json()
    prove(client, target)
    age_verification(client, target["id"], 31)
    assert client.get(f"{API}/targets/{target['id']}").json()["status"] == "reverify"
    response = client.post(
        f"{API}/scans", json={"url": "https://example.com/", "authorization_confirmed": True}
    )
    assert response.status_code == 403
    assert "expired" in response.json()["detail"] and "New challenge" in response.json()["detail"]


def test_the_old_challenge_cannot_renew_a_lapsed_proof(client: TestClient) -> None:
    target = create(client).json()
    prove(client, target)
    age_verification(client, target["id"], 31)
    asked = set_dns(client, {target["dns_record_name"]: [target["dns_record_value"]]})
    response = verify(client, target["id"])
    assert response.status_code == 409 and "New challenge" in response.json()["detail"]
    assert asked == []  # refused before any DNS lookup
    assert client.get(f"{API}/targets/{target['id']}").json()["status"] == "reverify"


def test_a_fresh_challenge_renews_the_proof_and_is_audited(client: TestClient) -> None:
    target = create(client).json()
    prove(client, target)
    age_verification(client, target["id"], 31)
    fresh = client.post(f"{API}/targets/{target['id']}/challenge").json()
    assert fresh["status"] == "reverify" and fresh["challenge_token"] != target["challenge_token"]
    # The previous token no longer proves anything.
    set_dns(client, {fresh["dns_record_name"]: [target["dns_record_value"]]})
    assert "does not match" in verify(client, target["id"]).json()["last_check_error"]
    renewed = prove(client, fresh)
    assert renewed["status"] == "verified" and renewed["last_check_error"] is None
    assert datetime.fromisoformat(renewed["verification_expires_at"]) > datetime.now(UTC) + timedelta(days=29)
    events = event_types(client)
    assert "target.reverified" in events and "target.challenge_regenerated" in events


def test_zero_days_means_proofs_never_expire(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(target_verification_valid_days=0), mailer)) as c:
        signup(c, "alice@example.com", "Alice Org")
        target = create(c).json()
        prove(c, target)
        age_verification(c, target["id"], 3650)
        body = c.get(f"{API}/targets/{target['id']}").json()
        assert body["status"] == "verified" and body["verification_expires_at"] is None
