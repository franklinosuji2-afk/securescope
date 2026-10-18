"""The audit log API: owners and admins only, scoped to one organization, newest first."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.tests.conftest import signup

URL = "/api/v1/audit-events"


def org_id(client: TestClient) -> str:
    return client.get("/api/v1/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def test_owner_sees_their_own_events_newest_first(strict_client: TestClient) -> None:
    strict_client.post("/api/v1/targets", json={"hostname": "a.example"})
    body = strict_client.get(URL).json()
    types = [e["event_type"] for e in body["items"]]
    assert types[0] == "target.created"  # newest first
    assert "user.registered" in types
    assert body["total"] == len(body["items"])
    first = body["items"][0]
    assert first["actor_email"] == "alice@example.com"
    assert first["resource_type"] == "target" and first["resource_id"]
    assert "target.created" in body["event_types"] and body["event_types"] == sorted(body["event_types"])


def test_filter_by_event_type_and_paginate(strict_client: TestClient) -> None:
    for host in ("a.example", "b.example", "c.example"):
        strict_client.post("/api/v1/targets", json={"hostname": host})
    page = strict_client.get(URL, params={"event_type": "target.created", "limit": 2, "offset": 0}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    rest = strict_client.get(URL, params={"event_type": "target.created", "limit": 2, "offset": 2}).json()
    assert len(rest["items"]) == 1
    seen = {e["id"] for e in page["items"]} | {e["id"] for e in rest["items"]}
    assert len(seen) == 3  # no overlap between pages
    assert all(e["event_type"] == "target.created" for e in page["items"] + rest["items"])
    assert strict_client.get(URL, params={"event_type": "nothing.here"}).json()["items"] == []


def test_invalid_parameters_are_rejected(strict_client: TestClient) -> None:
    assert strict_client.get(URL, params={"event_type": "x; DROP TABLE"}).status_code == 422
    assert strict_client.get(URL, params={"limit": 0}).status_code == 422
    assert strict_client.get(URL, params={"limit": 101}).status_code == 422
    assert strict_client.get(URL, params={"offset": -1}).status_code == 422


def test_requires_sign_in(anon_client: TestClient) -> None:
    assert anon_client.get(URL).status_code == 401


def test_other_organizations_never_see_these_events(strict_client: TestClient, bob_client: TestClient) -> None:
    strict_client.post("/api/v1/targets", json={"hostname": "alice-only.example"})
    bob_events = bob_client.get(URL).json()
    assert all(e["actor_email"] == "bob@example.com" for e in bob_events["items"])
    assert "target.created" not in bob_events["event_types"]
    # Naming alice's organization does not help: bob is not a member of it.
    stolen = bob_client.get(URL, headers={"X-Organization-Id": org_id(strict_client)})
    assert stolen.status_code == 403


def test_only_owners_and_admins_may_read(strict_client: TestClient, mailer, make_settings) -> None:  # type: ignore[no-untyped-def]
    org = org_id(strict_client)
    roles = {"ADMIN": 200, "SECURITY_ANALYST": 403, "MEMBER": 403, "VIEWER": 403}
    for role, expected in roles.items():
        email = f"{role.lower()}@example.com"
        other = TestClient(strict_client.app)
        signup(other, email, f"{role} personal org")
        added = strict_client.post(
            f"/api/v1/organizations/{org}/members", json={"email": email, "role": role}
        )
        assert added.status_code == 201, added.text
        response = other.get(URL, headers={"X-Organization-Id": org})
        assert response.status_code == expected, (role, response.text)
        if expected == 200:
            assert any(e["event_type"] == "org.member.added" for e in response.json()["items"])
