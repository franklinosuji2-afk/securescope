"""Cross-tenant isolation and role-based access control."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.tests.conftest import signup, trust_host

API = "/api/v1"


def new_user(app_client: TestClient, email: str) -> TestClient:
    client = TestClient(app_client.app)
    signup(client, email, f"{email} org")
    return client


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def add_member(owner: TestClient, org_id: str, email: str, role: str) -> Any:
    return owner.post(f"{API}/organizations/{org_id}/members", json={"email": email, "role": role})


def finished_scan(client: TestClient, mock_server: str, headers: dict[str, str] | None = None) -> str:
    response = client.post(
        f"{API}/scans",
        json={"url": f"{mock_server}/plain", "authorization_confirmed": True},
        headers=headers or {},
    )
    assert response.status_code == 202, response.text
    scan_id: str = response.json()["id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        detail = client.get(f"{API}/scans/{scan_id}", headers=headers or {}).json()
        if detail["status"] in ("completed", "failed"):
            return scan_id
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


# --- unauthenticated access ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/scans"),
        ("POST", "/scans"),
        ("GET", "/scans/abc"),
        ("GET", "/scans/abc/report"),
        ("GET", "/organizations"),
        ("POST", "/organizations"),
        ("GET", "/organizations/abc"),
        ("GET", "/auth/me"),
    ],
)
def test_protected_endpoints_require_authentication(anon_client: TestClient, method: str, path: str) -> None:
    assert anon_client.request(method, f"{API}{path}", json={}).status_code == 401


def test_unauthorised_scan_submission_creates_nothing(anon_client: TestClient) -> None:
    body = {"url": "https://example.org", "authorization_confirmed": True}
    assert anon_client.post(f"{API}/scans", json=body).status_code == 401
    assert anon_client.app.state.s.repo.list_scans("any")[1] == 0  # type: ignore[attr-defined]


# --- tenant isolation ---------------------------------------------------------------------------


def test_another_organization_cannot_read_scans(local_client: TestClient, mock_server: str) -> None:
    bob = new_user(local_client, "bob@example.com")
    scan_id = finished_scan(local_client, mock_server)

    assert local_client.get(f"{API}/scans/{scan_id}").status_code == 200
    assert bob.get(f"{API}/scans/{scan_id}").status_code == 404  # same answer as "does not exist"
    assert bob.get(f"{API}/scans/{scan_id}/report?format=json").status_code == 404
    assert bob.get(f"{API}/scans/{scan_id}/report?format=html").status_code == 404
    listing = bob.get(f"{API}/scans").json()
    assert listing["total"] == 0 and listing["items"] == []
    assert local_client.get(f"{API}/scans").json()["total"] == 1


def test_client_cannot_choose_an_organization_it_does_not_belong_to(
    local_client: TestClient, mock_server: str
) -> None:
    bob = new_user(local_client, "bob@example.com")
    alice_org = org_of(local_client)
    scan_id = finished_scan(local_client, mock_server)
    spoof = {"X-Organization-Id": alice_org}

    assert bob.get(f"{API}/scans", headers=spoof).status_code == 403
    assert bob.get(f"{API}/scans/{scan_id}", headers=spoof).status_code == 403
    body = {"url": f"{mock_server}/plain", "authorization_confirmed": True}
    assert bob.post(f"{API}/scans", json=body, headers=spoof).status_code == 403
    assert bob.get(f"{API}/scans", headers={"X-Organization-Id": "not-a-real-org"}).status_code == 403


def test_organization_details_and_management_are_hidden_from_outsiders(local_client: TestClient) -> None:
    bob = new_user(local_client, "bob@example.com")
    alice_org = org_of(local_client)
    assert bob.get(f"{API}/organizations/{alice_org}").status_code == 404
    assert add_member(bob, alice_org, "bob@example.com", "OWNER").status_code == 404
    assert bob.delete(f"{API}/organizations/{alice_org}/members/anyone").status_code == 404
    assert [o["id"] for o in bob.get(f"{API}/organizations").json()] != [alice_org]


def test_scans_are_scoped_to_the_active_organization(local_client: TestClient, mock_server: str) -> None:
    second = local_client.post(f"{API}/organizations", json={"name": "Second Org"}).json()
    in_second = {"X-Organization-Id": second["id"]}
    trust_host(local_client, "127.0.0.1", second["id"])  # verification is per organization
    scan_id = finished_scan(local_client, mock_server, in_second)

    assert local_client.get(f"{API}/scans", headers=in_second).json()["total"] == 1
    assert local_client.get(f"{API}/scans").json()["total"] == 0  # default org has none
    assert local_client.get(f"{API}/scans/{scan_id}").status_code == 404  # wrong active org
    assert local_client.get(f"{API}/scans/{scan_id}", headers=in_second).status_code == 200


def test_removed_member_loses_access_immediately(local_client: TestClient, mock_server: str) -> None:
    carol = new_user(local_client, "carol@example.com")
    org = org_of(local_client)
    carol_id = carol.get(f"{API}/auth/me").json()["id"]
    assert add_member(local_client, org, "carol@example.com", "VIEWER").status_code == 201
    scan_id = finished_scan(local_client, mock_server)
    assert carol.get(f"{API}/scans/{scan_id}", headers={"X-Organization-Id": org}).status_code == 200
    assert local_client.delete(f"{API}/organizations/{org}/members/{carol_id}").status_code == 204
    assert carol.get(f"{API}/scans/{scan_id}", headers={"X-Organization-Id": org}).status_code == 403


def test_isolation_holds_on_the_repository_layer(local_client: TestClient, mock_server: str) -> None:
    scan_id = finished_scan(local_client, mock_server)
    repo = local_client.app.state.s.repo  # type: ignore[attr-defined]
    assert repo.get_scan(scan_id, "some-other-org") is None
    assert repo.list_scans("some-other-org")[1] == 0


# --- roles --------------------------------------------------------------------------------------


def test_viewer_can_read_and_export_but_not_scan(local_client: TestClient, mock_server: str) -> None:
    viewer = new_user(local_client, "viewer@example.com")
    org = org_of(local_client)
    scan_id = finished_scan(local_client, mock_server)
    assert add_member(local_client, org, "viewer@example.com", "VIEWER").status_code == 201
    h = {"X-Organization-Id": org}

    assert viewer.get(f"{API}/scans", headers=h).json()["total"] == 1
    assert viewer.get(f"{API}/scans/{scan_id}/report?format=json", headers=h).status_code == 200
    body = {"url": f"{mock_server}/plain", "authorization_confirmed": True}
    assert viewer.post(f"{API}/scans", json=body, headers=h).status_code == 403


@pytest.mark.parametrize("role", ["MEMBER", "SECURITY_ANALYST", "ADMIN"])
def test_scanning_roles_can_start_scans(local_client: TestClient, mock_server: str, role: str) -> None:
    user = new_user(local_client, f"{role.lower()}@example.com")
    org = org_of(local_client)
    assert add_member(local_client, org, f"{role.lower()}@example.com", role).status_code == 201
    # Only the permission is asserted here: a client created outside `with TestClient` has no
    # long-lived event loop, so it cannot be used to wait for the background scan to finish.
    body = {"url": f"{mock_server}/plain", "authorization_confirmed": True}
    assert user.post(f"{API}/scans", json=body, headers={"X-Organization-Id": org}).status_code == 202


def test_only_owners_and_admins_manage_members(local_client: TestClient) -> None:
    org = org_of(local_client)
    for email, role in (("member@example.com", "MEMBER"), ("analyst@example.com", "SECURITY_ANALYST")):
        user = new_user(local_client, email)
        add_member(local_client, org, email, role)
        third = new_user(local_client, f"x{email}")
        assert add_member(user, org, f"x{email}", "VIEWER").status_code == 403
        assert third  # silence unused


def test_admin_cannot_escalate_or_touch_peers(local_client: TestClient) -> None:
    org = org_of(local_client)
    admin = new_user(local_client, "admin@example.com")
    add_member(local_client, org, "admin@example.com", "ADMIN")
    admin_id = admin.get(f"{API}/auth/me").json()["id"]
    other_admin = new_user(local_client, "admin2@example.com")
    add_member(local_client, org, "admin2@example.com", "ADMIN")
    admin2_id = other_admin.get(f"{API}/auth/me").json()["id"]
    new_user(local_client, "newbie@example.com")
    owner_id = local_client.get(f"{API}/auth/me").json()["id"]

    assert add_member(admin, org, "newbie@example.com", "OWNER").status_code == 403
    assert add_member(admin, org, "newbie@example.com", "ADMIN").status_code == 403
    assert add_member(admin, org, "newbie@example.com", "VIEWER").status_code == 201
    base = f"{API}/organizations/{org}/members"
    assert admin.patch(f"{base}/{admin_id}", json={"role": "OWNER"}).status_code == 403  # self-promotion
    assert admin.patch(f"{base}/{admin2_id}", json={"role": "VIEWER"}).status_code == 403
    assert admin.patch(f"{base}/{owner_id}", json={"role": "VIEWER"}).status_code == 403
    assert admin.delete(f"{base}/{owner_id}").status_code == 403
    assert admin.delete(f"{base}/{admin2_id}").status_code == 403


def test_an_organization_always_keeps_an_owner(local_client: TestClient) -> None:
    org = org_of(local_client)
    owner_id = local_client.get(f"{API}/auth/me").json()["id"]
    base = f"{API}/organizations/{org}/members/{owner_id}"
    assert local_client.patch(base, json={"role": "ADMIN"}).status_code == 409
    assert local_client.delete(base).status_code == 409
    new_user(local_client, "second@example.com")
    assert add_member(local_client, org, "second@example.com", "OWNER").status_code == 201
    assert local_client.patch(base, json={"role": "ADMIN"}).status_code == 200  # now allowed


def test_members_can_leave_but_not_remove_others(local_client: TestClient) -> None:
    org = org_of(local_client)
    member = new_user(local_client, "member@example.com")
    add_member(local_client, org, "member@example.com", "MEMBER")
    member_id = member.get(f"{API}/auth/me").json()["id"]
    owner_id = local_client.get(f"{API}/auth/me").json()["id"]
    base = f"{API}/organizations/{org}/members"
    h = {"X-Organization-Id": org}
    assert member.delete(f"{base}/{owner_id}", headers=h).status_code == 403
    assert member.delete(f"{base}/{member_id}", headers=h).status_code == 204


def test_duplicate_and_unknown_members(local_client: TestClient) -> None:
    org = org_of(local_client)
    new_user(local_client, "dup@example.com")
    assert add_member(local_client, org, "dup@example.com", "MEMBER").status_code == 201
    assert add_member(local_client, org, "dup@example.com", "MEMBER").status_code == 409
    assert add_member(local_client, org, "nobody@example.com", "MEMBER").status_code == 404
    assert (
        local_client.post(
            f"{API}/organizations/{org}/members", json={"email": "dup@example.com", "role": "GOD"}
        ).status_code
        == 422
    )


def test_role_changes_are_audited(local_client: TestClient) -> None:
    org = org_of(local_client)
    new_user(local_client, "audited@example.com")
    add_member(local_client, org, "audited@example.com", "VIEWER")
    types = local_client.app.state.s.audit.all_event_types()  # type: ignore[attr-defined]
    assert "org.member.added" in types
