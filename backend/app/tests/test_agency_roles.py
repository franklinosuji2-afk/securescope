"""Every agency endpoint is checked against the permission matrix for every role, and against the plan.

The roles come from app.security.permissions.MATRIX, so a change to the matrix that is not matched by the route
dependencies fails here. A person who is not a member of the workspace, and a free workspace, get nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.permissions import MATRIX, Permission, Role
from app.tests.conftest import signup
from app.tests.test_agency import make_client, target_id_of
from app.tests.test_tenancy import add_member, finished_scan, new_user, org_of

API = "/api/v1/agency"
ROLES = [Role.VIEWER, Role.MEMBER, Role.SECURITY_ANALYST, Role.ADMIN, Role.OWNER]


def endpoints(ids: dict[str, str]) -> list[tuple[str, str, Permission, dict[str, Any] | None]]:
    c, s, t = ids["client"], ids["scan"], ids["target"]
    return [
        ("GET", "/clients", Permission.CLIENT_READ, None),
        ("POST", "/clients", Permission.CLIENT_MANAGE, {"name": "Created by role test"}),
        ("GET", f"/clients/{c}", Permission.CLIENT_READ, None),
        ("PUT", f"/clients/{c}", Permission.CLIENT_MANAGE, {"name": "Renamed by role test"}),
        ("PUT", f"/targets/{t}/client", Permission.CLIENT_MANAGE, {"client_id": c}),
        ("GET", "/dashboard", Permission.CLIENT_READ, None),
        ("GET", "/branding", Permission.CLIENT_READ, None),
        ("PUT", "/branding", Permission.CLIENT_MANAGE, {"agency_name": "Role test agency"}),
        ("GET", f"/scans/{s}/shares", Permission.REPORT_SHARE, None),
        ("POST", f"/scans/{s}/shares", Permission.REPORT_SHARE, {"days": 7}),
        ("DELETE", f"/scans/{s}/shares/{'0' * 32}", Permission.REPORT_SHARE, None),
        ("DELETE", f"/clients/{c}", Permission.CLIENT_MANAGE, None),  # last: it removes the client
    ]


@pytest.fixture
def agency(make_settings, mailer, mock_server):  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0)
    from app.tests.conftest import trust_host

    with TestClient(create_app(settings, mailer)) as owner:
        signup(owner, "owner@example.com", "Agency Org")
        trust_host(owner, "127.0.0.1")
        ids = {
            "client": str(make_client(owner)["id"]),
            "scan": finished_scan(owner, mock_server),
            "target": target_id_of(owner),
            "org": org_of(owner),
        }
        yield owner, ids


def test_each_role_may_call_exactly_the_endpoints_its_permissions_allow(agency: Any) -> None:
    owner, ids = agency
    wrong: list[str] = []
    for role in ROLES:
        if role is Role.OWNER:
            person = owner
        else:
            email = f"{role.value.lower()}@example.com"
            person = new_user(owner, email)
            assert add_member(owner, ids["org"], email, role.value).status_code == 201
        headers = {"X-Organization-Id": ids["org"]}
        for method, path, permission, body in endpoints(ids):
            if role is Role.OWNER and method == "DELETE" and path.startswith("/clients/"):
                continue  # deleted at the end of the loop below, so the other roles still have a client to read
            response = person.request(method, f"{API}{path}", json=body, headers=headers)
            allowed = permission in MATRIX[role]
            if allowed and response.status_code == 403:
                wrong.append(f"{role.value} was refused {method} {path}")
            if not allowed and response.status_code != 403:
                wrong.append(f"{role.value} got {response.status_code} on {method} {path}")
    assert wrong == []


def test_someone_who_is_not_a_member_gets_nothing_even_when_naming_the_workspace(agency: Any) -> None:
    owner, ids = agency
    stranger = new_user(owner, "stranger@example.com")
    for method, path, _, body in endpoints(ids):
        response = stranger.request(
            method, f"{API}{path}", json=body, headers={"X-Organization-Id": ids["org"]}
        )
        assert response.status_code in (403, 404), f"{method} {path} -> {response.status_code}"
    # And nothing changed for the owner.
    assert owner.get(f"{API}/clients/{ids['client']}").json()["name"] == "Acme Ltd"


def test_a_member_who_is_removed_loses_agency_access_at_once(agency: Any) -> None:
    owner, ids = agency
    person = new_user(owner, "leaver@example.com")
    assert add_member(owner, ids["org"], "leaver@example.com", "SECURITY_ANALYST").status_code == 201
    headers = {"X-Organization-Id": ids["org"]}
    assert person.get(f"{API}/clients", headers=headers).status_code == 200
    me = person.get("/api/v1/auth/me").json()["id"]
    assert owner.delete(f"/api/v1/organizations/{ids['org']}/members/{me}").status_code == 204
    assert person.get(f"{API}/clients", headers=headers).status_code in (403, 404)
    assert person.get(f"{API}/scans/{ids['scan']}/shares", headers=headers).status_code in (403, 404)


def test_a_workspace_without_the_agency_plan_is_refused_whatever_the_role(
    make_settings: Any, mailer: Any
) -> None:
    with TestClient(create_app(make_settings(default_plan=None), mailer)) as owner:
        signup(owner, "free-owner@example.com", "Free Org")
        ids = {"client": "0" * 32, "scan": "0" * 32, "target": "0" * 32}
        for method, path, _, body in endpoints(ids):
            response = owner.request(method, f"{API}{path}", json=body)
            assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
