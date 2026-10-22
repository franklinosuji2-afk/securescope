"""Agency workspace: clients, dashboard, branding and shared report links, with strict tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select, update

from app.main import create_app
from app.models.agency import ReportShareRow
from app.models.scan import ReportRow
from app.security.permissions import Permission, Role, can
from app.tests.conftest import signup
from app.tests.test_tenancy import add_member, finished_scan, new_user, org_of

API = "/api/v1/agency"
SECRET_NOTE = "PRIVATE-NOTE-7Q2X"
SECRET_MAIL = "boss.private@client-secret.example"


def pdf_text(content: bytes) -> str:
    return " ".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def make_client(client: TestClient, name: str = "Acme Ltd", **extra: object) -> dict[str, object]:
    body = {"name": name, "contact_email": SECRET_MAIL, "notes": SECRET_NOTE, **extra}
    created = client.post(f"{API}/clients", json=body)
    assert created.status_code == 201, created.text
    return created.json()  # type: ignore[no-any-return]


def target_id_of(client: TestClient, host: str = "127.0.0.1") -> str:
    items = client.get("/api/v1/targets").json()["items"]
    return str(next(t["id"] for t in items if t["hostname"] == host))


@pytest.fixture
def anon(local_client: TestClient) -> TestClient:
    """A visitor with no session, as someone opening a shared link."""
    return TestClient(local_client.app)


@pytest.fixture
def free_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(default_plan=None), mailer)) as client:
        signup(client, "free@example.com", "Free Org")
        yield client


# --- plan and role gating -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/clients"),
        ("POST", "/clients"),
        ("GET", "/dashboard"),
        ("GET", "/branding"),
        ("PUT", "/branding"),
        ("POST", "/scans/abc/shares"),
    ],
)
def test_a_free_workspace_gets_none_of_it(free_client: TestClient, method: str, path: str) -> None:
    body = (
        {"name": "x"} if path == "/clients" else {"agency_name": "x"} if path == "/branding" else {"days": 7}
    )
    response = free_client.request(method, f"{API}{path}", json=body)
    assert response.status_code == 403
    assert "Agency plan" in response.json()["detail"]


def test_the_plan_summary_says_whether_client_workspaces_are_included(
    free_client: TestClient, local_client: TestClient
) -> None:
    free = free_client.get(f"/api/v1/organizations/{org_of(free_client)}/plan").json()
    internal = local_client.get(f"/api/v1/organizations/{org_of(local_client)}/plan").json()
    assert free["limits"]["client_workspace"] is False
    assert internal["limits"]["client_workspace"] is True


def test_nothing_here_works_without_signing_in(anon_client: TestClient) -> None:
    for method, path in (("GET", "/clients"), ("GET", "/dashboard"), ("POST", "/scans/abc/shares")):
        assert anon_client.request(method, f"{API}{path}").status_code == 401


def test_the_permission_matrix_keeps_clients_away_from_viewers() -> None:
    for permission in (Permission.CLIENT_READ, Permission.CLIENT_MANAGE, Permission.REPORT_SHARE):
        assert not can(Role.VIEWER, permission)
    assert can(Role.SECURITY_ANALYST, Permission.CLIENT_READ) and can(
        Role.SECURITY_ANALYST, Permission.REPORT_SHARE
    )
    assert not can(Role.SECURITY_ANALYST, Permission.CLIENT_MANAGE)
    assert can(Role.MEMBER, Permission.CLIENT_READ) and not can(Role.MEMBER, Permission.REPORT_SHARE)
    assert can(Role.OWNER, Permission.CLIENT_MANAGE) and can(Role.ADMIN, Permission.CLIENT_MANAGE)


@pytest.mark.parametrize(
    ("role", "can_read", "can_manage", "can_share"),
    [
        ("VIEWER", False, False, False),
        ("MEMBER", True, False, False),
        ("SECURITY_ANALYST", True, False, True),
        ("ADMIN", True, True, True),
    ],
)
def test_roles_are_enforced_by_the_server(
    local_client: TestClient, role: str, can_read: bool, can_manage: bool, can_share: bool
) -> None:
    email = f"{role.lower()}@example.com"
    user = new_user(local_client, email)
    org = org_of(local_client)
    assert add_member(local_client, org, email, role).status_code == 201
    h = {"X-Organization-Id": org}
    assert (user.get(f"{API}/clients", headers=h).status_code == 200) is can_read
    assert (user.post(f"{API}/clients", json={"name": "N"}, headers=h).status_code == 201) is can_manage
    shares = user.get(f"{API}/scans/abc/shares", headers=h).status_code
    assert (shares != 403) is can_share


# --- clients ----------------------------------------------------------------------------------------


def test_clients_can_be_created_changed_listed_and_deleted(local_client: TestClient) -> None:
    created = make_client(local_client)
    assert created["name"] == "Acme Ltd" and created["site_count"] == 0
    listing = local_client.get(f"{API}/clients").json()["items"]
    assert [c["id"] for c in listing] == [created["id"]]
    updated = local_client.put(f"{API}/clients/{created['id']}", json={"name": "Acme GmbH", "notes": "new"})
    assert updated.status_code == 200 and updated.json()["name"] == "Acme GmbH"
    assert local_client.delete(f"{API}/clients/{created['id']}").status_code == 204
    assert local_client.get(f"{API}/clients/{created['id']}").status_code == 404
    assert local_client.get(f"{API}/clients").json()["items"] == []


def test_client_input_is_validated(local_client: TestClient) -> None:
    assert local_client.post(f"{API}/clients", json={"name": "   "}).status_code == 422
    assert (
        local_client.post(f"{API}/clients", json={"name": "A", "contact_email": "not an email"}).status_code
        == 422
    )
    assert local_client.post(f"{API}/clients", json={"name": "A", "notes": "x" * 2001}).status_code == 422
    assert local_client.post(f"{API}/clients", json={"name": "A", "surprise": 1}).status_code == 422
    assert local_client.post(f"{API}/clients", json={"name": "N" * 121}).status_code == 422


def test_names_are_unique_inside_a_workspace_but_not_across_workspaces(local_client: TestClient) -> None:
    make_client(local_client, "Same Name")
    assert local_client.post(f"{API}/clients", json={"name": "Same Name"}).status_code == 409
    other = new_user(local_client, "other@example.com")
    assert other.post(f"{API}/clients", json={"name": "Same Name"}).status_code == 201


def test_deleting_a_client_keeps_its_websites(local_client: TestClient) -> None:
    created = make_client(local_client)
    site = target_id_of(local_client)
    assert (
        local_client.put(f"{API}/targets/{site}/client", json={"client_id": created["id"]}).status_code == 204
    )
    assert local_client.get(f"{API}/clients/{created['id']}").json()["site_count"] == 1
    assert local_client.delete(f"{API}/clients/{created['id']}").status_code == 204
    assert site in [t["id"] for t in local_client.get("/api/v1/targets").json()["items"]]
    dashboard = local_client.get(f"{API}/dashboard").json()
    assert [c["client_id"] for c in dashboard["clients"]] == [None]


# --- isolation --------------------------------------------------------------------------------------


def test_another_workspace_cannot_see_change_or_delete_a_client(local_client: TestClient) -> None:
    mine = make_client(local_client)
    bob = new_user(local_client, "bob@example.com")
    assert bob.get(f"{API}/clients").json()["items"] == []
    assert bob.get(f"{API}/clients/{mine['id']}").status_code == 404
    assert bob.put(f"{API}/clients/{mine['id']}", json={"name": "Hijacked"}).status_code == 404
    assert bob.delete(f"{API}/clients/{mine['id']}").status_code == 404
    assert local_client.get(f"{API}/clients/{mine['id']}").json()["name"] == "Acme Ltd"


def test_a_website_can_only_be_put_under_a_client_of_the_same_workspace(local_client: TestClient) -> None:
    mine = make_client(local_client)
    my_site = target_id_of(local_client)
    bob = new_user(local_client, "bob@example.com")
    bobs_site = bob.post("/api/v1/targets", json={"hostname": "bob.example.com"}).json()["id"]
    bobs_client = make_client(bob, "Bob's client")

    # Bob cannot attach his site to Alice's client, nor touch Alice's site.
    assert bob.put(f"{API}/targets/{bobs_site}/client", json={"client_id": mine["id"]}).status_code == 404
    assert (
        bob.put(f"{API}/targets/{my_site}/client", json={"client_id": bobs_client["id"]}).status_code == 404
    )
    # Alice cannot put her site under Bob's client either.
    assert (
        local_client.put(f"{API}/targets/{my_site}/client", json={"client_id": bobs_client["id"]}).status_code
        == 404
    )
    assert local_client.get(f"{API}/clients/{mine['id']}").json()["site_count"] == 0
    assert bob.get(f"{API}/clients/{bobs_client['id']}").json()["site_count"] == 0


def test_the_dashboard_only_ever_shows_the_signed_in_workspace(
    local_client: TestClient, mock_server: str
) -> None:
    mine = make_client(local_client, "Alice's client")
    local_client.put(f"{API}/targets/{target_id_of(local_client)}/client", json={"client_id": mine["id"]})
    finished_scan(local_client, mock_server)
    bob = new_user(local_client, "bob@example.com")
    empty = bob.get(f"{API}/dashboard").json()
    assert empty == {"clients": [], "total_sites": 0, "total_clients": 0}
    assert "127.0.0.1" not in str(empty) and "Alice" not in str(empty)


# --- dashboard --------------------------------------------------------------------------------------


def test_an_empty_workspace_has_an_empty_dashboard(local_client: TestClient) -> None:
    dashboard = local_client.get(f"{API}/dashboard").json()
    assert (
        dashboard["total_clients"] == 0 and dashboard["total_sites"] == 1
    )  # the one trusted site, unassigned
    assert [c["name"] for c in dashboard["clients"]] == ["Not assigned to a client"]
    assert dashboard["clients"][0]["sites"][0]["score"] is None  # never scanned: no invented numbers


def test_the_dashboard_reports_stored_scan_results_and_nothing_else(
    local_client: TestClient, mock_server: str
) -> None:
    created = make_client(local_client)
    local_client.put(f"{API}/targets/{target_id_of(local_client)}/client", json={"client_id": created["id"]})
    scan_id = finished_scan(local_client, mock_server)
    detail = local_client.get(f"/api/v1/scans/{scan_id}").json()
    row = local_client.get(f"{API}/dashboard").json()["clients"][0]
    site = row["sites"][0]
    assert row["client_id"] == created["id"] and row["name"] == "Acme Ltd"
    assert (
        site["last_scan_id"] == scan_id
        and site["score"] == detail["score"]
        and site["grade"] == detail["grade"]
    )
    open_now = sum(1 for f in detail["findings"] if f["status"] == "open")
    assert sum(site["open_findings"].values()) == open_now > 0
    assert row["worst_grade"] == detail["grade"]


# --- branding ---------------------------------------------------------------------------------------


def test_the_agency_name_is_printed_on_new_reports_and_attribution_stays(
    local_client: TestClient, mock_server: str
) -> None:
    name = "Nordlicht <b>Security</b> & Co"
    assert local_client.put(f"{API}/branding", json={"agency_name": name}).json()["agency_name"] == name
    scan_id = finished_scan(local_client, mock_server)
    link = local_client.get(f"/api/v1/scans/{scan_id}/report/pdf").json()["url"]
    text = pdf_text(local_client.get(link).content)
    assert "Prepared by" in text and "Nordlicht <b>Security</b> & Co" in text  # printed as text, not markup
    assert "generated by SecureScope" in text


def test_reports_without_branding_do_not_claim_one(local_client: TestClient, mock_server: str) -> None:
    scan_id = finished_scan(local_client, mock_server)
    link = local_client.get(f"/api/v1/scans/{scan_id}/report/pdf").json()["url"]
    assert "Prepared by" not in pdf_text(local_client.get(link).content)


# --- shared report links ----------------------------------------------------------------------------


def make_share(client: TestClient, scan_id: str, days: int = 30) -> dict[str, object]:
    response = client.post(f"{API}/scans/{scan_id}/shares", json={"days": days})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_a_share_link_opens_one_report_without_signing_in(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    scan_id = finished_scan(local_client, mock_server)
    share = make_share(local_client, scan_id)
    token = str(share["token"])
    assert share["status"] == "active" and len(token) >= 40

    info = anon.get(f"/api/v1/shared/{token}")
    assert info.status_code == 200
    assert set(info.json()) == {
        "host",
        "scanned_at",
        "score",
        "grade",
        "prepared_by",
        "expires_at",
        "download_path",
    }
    pdf = anon.get(f"/api/v1/shared/{token}/report.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["cache-control"] == "private, no-store"
    assert "noindex" in pdf.headers["x-robots-tag"] and pdf.headers["referrer-policy"] == "no-referrer"
    listed = local_client.get(f"{API}/scans/{scan_id}/shares").json()["items"][0]
    assert listed["view_count"] == 1 and listed["last_viewed_at"] is not None
    assert "token" not in listed


def test_only_a_hash_of_the_secret_is_stored(local_client: TestClient, mock_server: str) -> None:
    scan_id = finished_scan(local_client, mock_server)
    token = str(make_share(local_client, scan_id)["token"])
    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.agency._session() as session:  # noqa: SLF001
        row = session.scalar(select(ReportShareRow))
        assert row is not None and row.token_hash != token and token not in str(vars(row))
    assert len(row.token_hash) == 64


def test_a_revoked_link_stops_working_everywhere(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    scan_id = finished_scan(local_client, mock_server)
    share = make_share(local_client, scan_id)
    token = str(share["token"])
    assert local_client.delete(f"{API}/scans/{scan_id}/shares/{share['id']}").status_code == 204
    assert anon.get(f"/api/v1/shared/{token}").status_code == 404
    assert anon.get(f"/api/v1/shared/{token}/report.pdf").status_code == 404
    assert local_client.get(f"{API}/scans/{scan_id}/shares").json()["items"][0]["status"] == "revoked"


def test_an_expired_link_stops_working(local_client: TestClient, anon: TestClient, mock_server: str) -> None:
    scan_id = finished_scan(local_client, mock_server)
    token = str(make_share(local_client, scan_id, days=7)["token"])
    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.agency._session.begin() as session:  # noqa: SLF001
        session.execute(update(ReportShareRow).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    assert anon.get(f"/api/v1/shared/{token}").status_code == 404
    assert local_client.get(f"{API}/scans/{scan_id}/shares").json()["items"][0]["status"] == "expired"


def test_unknown_malformed_and_revoked_links_all_look_the_same(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    scan_id = finished_scan(local_client, mock_server)
    share = make_share(local_client, scan_id)
    local_client.delete(f"{API}/scans/{scan_id}/shares/{share['id']}")
    answers = {
        anon.get(f"/api/v1/shared/{t}").text for t in (str(share["token"]), "A" * 43, "short", "x" * 300)
    }
    assert len(answers) == 1


def test_a_link_opens_only_its_own_report(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    first = finished_scan(local_client, mock_server)
    second = finished_scan(local_client, mock_server)
    token_first = str(make_share(local_client, first)["token"])
    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.agency._session() as session:  # noqa: SLF001
        content = {r.scan_id: bytes(r.content) for r in session.scalars(select(ReportRow))}
    got = anon.get(f"/api/v1/shared/{token_first}/report.pdf").content
    assert got == content[first]
    assert second not in content or got != content[second]
    # the link is not a key to the rest of the workspace
    assert anon.get(f"/api/v1/scans/{second}").status_code == 401
    assert anon.get(f"{API}/clients").status_code == 401


def test_another_workspace_cannot_share_list_or_revoke_a_report_it_does_not_own(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    scan_id = finished_scan(local_client, mock_server)
    share = make_share(local_client, scan_id)
    bob = new_user(local_client, "bob@example.com")
    assert bob.post(f"{API}/scans/{scan_id}/shares", json={"days": 7}).status_code == 404
    assert bob.get(f"{API}/scans/{scan_id}/shares").json()["items"] == []
    assert bob.delete(f"{API}/scans/{scan_id}/shares/{share['id']}").status_code == 404
    assert anon.get(f"/api/v1/shared/{share['token']}").status_code == 200  # still alive


def test_client_details_and_notes_never_reach_a_shared_or_downloaded_report(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    created = make_client(local_client)
    local_client.put(f"{API}/targets/{target_id_of(local_client)}/client", json={"client_id": created["id"]})
    scan_id = finished_scan(local_client, mock_server)
    token = str(make_share(local_client, scan_id)["token"])
    info = anon.get(f"/api/v1/shared/{token}").text
    pdf = pdf_text(anon.get(f"/api/v1/shared/{token}/report.pdf").content)
    for private in (SECRET_NOTE, SECRET_MAIL, "Acme Ltd"):
        assert private not in info and private not in pdf


def test_sharing_needs_a_finished_scan_and_a_valid_length(local_client: TestClient, mock_server: str) -> None:
    assert local_client.post(f"{API}/scans/doesnotexist/shares", json={"days": 7}).status_code == 404
    scan_id = finished_scan(local_client, mock_server)
    assert local_client.post(f"{API}/scans/{scan_id}/shares", json={"days": 365}).status_code == 422
    assert local_client.post(f"{API}/scans/{scan_id}/shares", json={"days": 7, "x": 1}).status_code == 422


def test_the_public_endpoint_is_rate_limited(local_client: TestClient, anon: TestClient) -> None:
    from app.middleware.ratelimit import SlidingWindowLimiter

    local_client.app.state.s.share_limiter = SlidingWindowLimiter(3)  # type: ignore[attr-defined]
    codes = [anon.get(f"/api/v1/shared/{'a' * 43}").status_code for _ in range(5)]
    assert codes[:3] == [404, 404, 404] and codes[3:] == [429, 429]


def test_deleting_a_scan_takes_its_share_links_with_it(
    local_client: TestClient, anon: TestClient, mock_server: str
) -> None:
    scan_id = finished_scan(local_client, mock_server)
    token = str(make_share(local_client, scan_id)["token"])
    assert local_client.delete(f"/api/v1/scans/{scan_id}").status_code in (200, 204)
    assert anon.get(f"/api/v1/shared/{token}").status_code == 404


def test_actions_are_written_to_the_audit_log(local_client: TestClient, mock_server: str) -> None:
    created = make_client(local_client)
    scan_id = finished_scan(local_client, mock_server)
    share = make_share(local_client, scan_id)
    local_client.delete(f"{API}/scans/{scan_id}/shares/{share['id']}")
    local_client.delete(f"{API}/clients/{created['id']}")
    events = {e["event_type"] for e in local_client.get("/api/v1/audit-events").json()["items"]}
    assert {"client.created", "share.created", "share.revoked", "client.deleted"} <= events
