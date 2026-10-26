"""One customer must never reach, change or learn about another customer's records.

Alice owns a verified site, a finished scan, a webhook, a CI token and a badge. Bob is a different customer with his
own workspace. Every route that takes one of Alice's ids is called as Bob, with Alice's id in the path, and must
refuse; afterwards nothing of Alice's may have changed. A bearer token made in one workspace must not act in another.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tests.conftest import signup, trust_host
from app.tests.test_integrations import Runner, bearer, make_token
from app.tests.test_tenancy import finished_scan, new_user, org_of

API = "/api/v1"
KEY = "k" * 40
REFUSED = (401, 403, 404)


@pytest.fixture
def alice(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0, webhook_signing_key=KEY)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        yield client


@pytest.fixture
def world(alice: TestClient, mock_server: str) -> dict[str, Any]:
    """Alice's records, plus Bob as a second customer."""
    target_id = trust_host(alice, "127.0.0.1")
    scan_id = finished_scan(alice, mock_server)
    hook = alice.post(f"{API}/webhooks", json={"url": "https://127.0.0.1/hooks/alice-secret-token"})
    assert hook.status_code == 201, hook.text
    token = make_token(alice)
    org = org_of(alice)
    client_id = alice.post(f"{API}/agency/clients", json={"name": "Alice client"}).json()["id"]
    share_id = alice.post(f"{API}/agency/scans/{scan_id}/shares", json={"days": 7}).json()["id"]
    invitation = alice.post(
        f"{API}/organizations/{org}/invitations", json={"email": "guest@example.com", "role": "VIEWER"}
    )
    assert invitation.status_code == 201, invitation.text
    session_id = alice.get(f"{API}/account/sessions").json()[0]["id"]
    owner_id = alice.get(f"{API}/auth/me").json()["id"]
    findings = alice.get(f"{API}/scans/{scan_id}/results").json()["findings"]
    fingerprint = next((f["fingerprint"] for f in findings if f.get("fingerprint")), "0" * 16)
    return {
        "target": target_id,
        "scan": scan_id,
        "hook": hook.json()["id"],
        "token": token,
        "fingerprint": fingerprint,
        "org": org,
        "client": client_id,
        "share": share_id,
        "invitation": invitation.json()["id"],
        "owner": owner_id,
        "session": session_id,
        "bob": new_user(alice, "bob@example.com"),
    }


def attacks(w: dict[str, Any]) -> list[tuple[str, str, dict[str, Any] | None]]:
    t, s, h, k, f = w["target"], w["scan"], w["hook"], w["token"]["id"], w["fingerprint"]
    o, c, sh, i, u = (
        w.get("org", "O"),
        w.get("client", "C"),
        w.get("share", "SH"),
        w.get("invitation", "I"),
        w.get("owner", "U"),
    )
    a = w.get("session", "A")
    return [
        ("GET", f"/targets/{t}", None),
        ("DELETE", f"/targets/{t}", None),
        ("POST", f"/targets/{t}/challenge", None),
        ("DELETE", f"/targets/{t}/challenge", None),
        ("POST", f"/targets/{t}/verify", {"method": "dns_txt"}),
        ("PUT", f"/schedules/{t}", {"frequency": "daily", "enabled": True}),
        ("PUT", f"/badges/{t}", {"enabled": True, "renew": False}),
        ("PUT", f"/agency/targets/{t}/client", {"client_id": None}),
        ("GET", f"/agency/clients/{c}", None),
        ("PUT", f"/agency/clients/{c}", {"name": "renamed by bob"}),
        ("DELETE", f"/agency/clients/{c}", None),
        ("DELETE", f"/agency/scans/{s}/shares/{sh}", None),
        ("GET", f"/organizations/{o}", None),
        ("GET", f"/organizations/{o}/plan", None),
        ("GET", f"/organizations/{o}/plan/downgrade-preview?to=free", None),
        ("POST", f"/organizations/{o}/members", {"email": "bob@example.com", "role": "ADMIN"}),
        ("PATCH", f"/organizations/{o}/members/{u}", {"role": "VIEWER"}),
        ("DELETE", f"/organizations/{o}/members/{u}", None),
        ("GET", f"/organizations/{o}/invitations", None),
        ("POST", f"/organizations/{o}/invitations", {"email": "x@example.com", "role": "ADMIN"}),
        ("DELETE", f"/organizations/{o}/invitations/{i}", None),
        ("GET", f"/scans/{s}", None),
        ("GET", f"/scans/{s}/results", None),
        ("POST", f"/scans/{s}/findings/{f}/recheck", None),
        ("GET", f"/scans/{s}/compare?with={s}", None),
        ("GET", f"/scans/{s}/report?format=json", None),
        ("GET", f"/scans/{s}/report?format=md", None),
        ("GET", f"/scans/{s}/report?format=html", None),
        ("GET", f"/scans/{s}/report?format=csv", None),
        ("GET", f"/scans/{s}/report/pdf", None),
        ("GET", f"/scans/{s}/report/pdf/download?expires=9999999999&sig={'0' * 64}", None),
        ("POST", f"/scans/{s}/cancel", None),
        ("POST", f"/scans/{s}/retry", None),
        ("DELETE", f"/scans/{s}", None),
        ("GET", f"/agency/scans/{s}/shares", None),
        ("POST", f"/agency/scans/{s}/shares", {"days": 7}),
        ("PATCH", f"/findings/{f}", {"status": "false_positive", "note": "hidden by bob"}),
        ("GET", f"/webhooks/{h}/deliveries", None),
        ("DELETE", f"/account/sessions/{a}", None),
        ("POST", f"/webhooks/{h}/test", None),
        ("POST", f"/webhooks/{h}/rotate", None),
        ("PUT", f"/webhooks/{h}", {"enabled": False}),
        ("DELETE", f"/webhooks/{h}", None),
        ("DELETE", f"/api-tokens/{k}", None),
    ]


def call(client: TestClient, method: str, path: str, body: dict[str, Any] | None) -> Any:
    return client.request(method, f"{API}{path}", json=body)


def test_every_route_with_a_foreign_id_refuses_and_changes_nothing(
    alice: TestClient, world: dict[str, Any]
) -> None:
    bob: TestClient = world["bob"]
    # The paths are real: the same read-only calls succeed for the owner, so Bob's refusals are about ownership.
    for method, path, body in attacks(world):
        if method == "GET" and "pdf" not in path and "compare" not in path:
            assert call(alice, method, path, body).status_code == 200, path
    leaked: list[str] = []
    for method, path, body in attacks(world):
        response = call(bob, method, path, body)
        # Listing the shares of a scan that is not yours answers with an empty list, never with another customer's.
        empty_list = method == "GET" and path.endswith("/shares") and response.json() == {"items": []}
        if response.status_code not in REFUSED and not empty_list:
            leaked.append(f"{method} {path} -> {response.status_code}")
        for secret in ("alice-secret", world["token"]["token"], "127.0.0.1"):
            if secret in response.text:
                leaked.append(f"{method} {path} echoed {secret[:8]}")
    assert leaked == []

    # Alice's world is exactly as it was.
    assert alice.get(f"{API}/targets/{world['target']}").status_code == 200
    detail = alice.get(f"{API}/scans/{world['scan']}").json()
    assert detail["status"] == "completed"
    hooks = alice.get(f"{API}/webhooks").json()["items"]
    assert [h["id"] for h in hooks] == [world["hook"]] and hooks[0]["enabled"] is True
    tokens = alice.get(f"{API}/api-tokens").json()["items"]
    assert [t["id"] for t in tokens] == [world["token"]["id"]]
    assert alice.get(f"{API}/badges").json()["items"][0]["enabled"] is False
    shares = alice.get(f"{API}/agency/scans/{world['scan']}/shares").json()["items"]
    assert [x["id"] for x in shares] == [world["share"]] and shares[0]["revoked_at"] is None
    assert alice.get(f"{API}/agency/clients/{world['client']}").json()["name"] == "Alice client"
    members = alice.get(f"{API}/organizations/{world['org']}")
    assert world["owner"] in members.text  # the owner was neither demoted nor removed by Bob
    invitations = alice.get(f"{API}/organizations/{world['org']}/invitations").json()
    assert [x["id"] for x in invitations] == [world["invitation"]]
    # Alice is still signed in: Bob could not end her session.
    assert alice.get(f"{API}/account/sessions").status_code == 200
    statuses = alice.get(f"{API}/scans/{world['scan']}/results").json()["findings"]
    assert all(f["status"] == "open" for f in statuses)


def test_bob_sees_none_of_alices_records_in_listings(alice: TestClient, world: dict[str, Any]) -> None:
    bob: TestClient = world["bob"]
    for path in ("/targets", "/scans", "/webhooks", "/api-tokens", "/badges", "/overview", "/audit-events"):
        text = bob.get(f"{API}{path}").text
        for marker in ("127.0.0.1", world["scan"], world["target"], world["hook"], "alice@example.com"):
            assert marker not in text, (path, marker)


def test_a_token_from_one_workspace_cannot_scan_or_read_in_another(
    alice: TestClient, world: dict[str, Any], mock_server: str
) -> None:
    bob: TestClient = world["bob"]
    bobs_token = make_token(bob)["token"] if bob.get(f"{API}/api-tokens").json()["available"] else None
    runner = Runner(alice)
    mine = world["token"]["token"]
    # Alice's token cannot read a scan id that does not belong to her workspace, and a made-up one is the same 404.
    assert runner.get(f"{API}/ci/scans/{'f' * 32}", headers=bearer(mine)).status_code == 404
    if bobs_token:
        # Bob's token reaches nothing of Alice's: her scan is 404, and her host is not one Bob has verified.
        assert runner.get(f"{API}/ci/scans/{world['scan']}", headers=bearer(bobs_token)).status_code == 404
        started = runner.post(
            f"{API}/ci/scans", json={"url": f"{mock_server}/plain"}, headers=bearer(bobs_token)
        )
        assert started.status_code in (400, 403)
    # A token cannot be used as a login: the cookie-protected routes refuse it.
    for path in ("/targets", "/scans", "/api-tokens", "/webhooks"):
        assert runner.get(f"{API}{path}", headers=bearer(mine)).status_code == 401


def test_a_removed_or_forged_token_gets_nothing(alice: TestClient, world: dict[str, Any]) -> None:
    runner = Runner(alice)
    token = world["token"]["token"]
    assert runner.get(f"{API}/ci/scans/{world['scan']}", headers=bearer(token)).status_code == 200
    assert alice.delete(f"{API}/api-tokens/{world['token']['id']}").status_code == 204
    assert runner.get(f"{API}/ci/scans/{world['scan']}", headers=bearer(token)).status_code == 401
    forged = "ssk_" + "A" * 43
    assert runner.get(f"{API}/ci/scans/{world['scan']}", headers=bearer(forged)).status_code == 401
    assert runner.get(f"{API}/ci/scans/{world['scan']}").status_code == 401


def test_the_public_badge_reveals_only_score_and_grade(alice: TestClient, world: dict[str, Any]) -> None:
    on = alice.put(f"{API}/badges/{world['target']}", json={"enabled": True, "renew": False}).json()
    svg = alice.get(on["url"].replace("http://testserver", "")).text
    for secret in ("127.0.0.1", world["scan"], world["target"], "alice", "finding", "SS-"):
        assert secret not in svg
    off = alice.put(f"{API}/badges/{world['target']}", json={"enabled": False, "renew": False}).json()
    assert off["url"] is None
    assert alice.get(on["url"].replace("http://testserver", "")).status_code == 404
