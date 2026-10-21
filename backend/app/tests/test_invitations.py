"""Invitations by email: single-use links tied to one address, with roles enforced by the server."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models.account import AuditEventRow, InvitationRow, UserRow
from app.tests.conftest import CapturingMailer, signup

API = "/api/v1"


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def person(owner: TestClient, email: str, *, verified: bool = True) -> TestClient:
    """A separate signed-in session for `email`, with the address confirmed unless told otherwise."""
    client = TestClient(owner.app)
    signup(client, email, f"{email} org")
    if verified:
        with owner.app.state.s.engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                update(UserRow).where(UserRow.email == email.lower()).values(email_verified_at=datetime.now(UTC))
            )
    return client


def invite(owner: TestClient, org: str, email: str, role: str = "VIEWER") -> Any:
    return owner.post(f"{API}/organizations/{org}/invitations", json={"email": email, "role": role})


def token_in(mailer: CapturingMailer) -> str:
    match = re.search(r"accept-invite\?token=([A-Za-z0-9_-]+)", mailer.sent[-1][2])
    assert match, mailer.sent[-1][2]
    return match.group(1)


def accept(client: TestClient, token: str) -> Any:
    return client.post(f"{API}/invitations/accept", json={"token": token})


def test_owner_invites_and_the_mail_carries_a_link(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    response = invite(strict_client, org, "Client@Example.com")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "client@example.com"
    assert body["role"] == "VIEWER"
    assert body["invited_by_email"] == "alice@example.com"
    to, subject, text = mailer.sent[-1]
    assert to == "client@example.com"
    assert "Alice Org" in subject
    assert "accept-invite?token=" in text
    assert "alice@example.com" in text
    pending = strict_client.get(f"{API}/organizations/{org}/invitations").json()
    assert [p["email"] for p in pending] == ["client@example.com"]
    # The list never contains the link or its digest.
    assert "token" not in str(pending)


def test_the_link_shows_what_it_is_for_before_anyone_signs_in(
    strict_client: TestClient, anon_client: TestClient, mailer: CapturingMailer
) -> None:
    invite(strict_client, org_of(strict_client), "client@example.com")
    token = token_in(mailer)
    preview = anon_client.get(f"{API}/invitations/preview", params={"token": token})
    assert preview.status_code == 200
    assert preview.json() == {
        "organization_name": "Alice Org",
        "email": "client@example.com",
        "role": "VIEWER",
    }
    assert anon_client.get(f"{API}/invitations/preview", params={"token": "x" * 40}).status_code == 404
    assert anon_client.get(f"{API}/invitations/preview", params={"token": "short"}).status_code == 422


def test_accepting_joins_the_workspace_once(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "client@example.com")
    token = token_in(mailer)
    client = person(strict_client, "client@example.com")
    response = accept(client, token)
    assert response.status_code == 200, response.text
    assert response.json() == {"organization_id": org}
    mine = {o["id"]: o["role"] for o in client.get(f"{API}/auth/me").json()["organizations"]}
    assert mine[org] == "VIEWER"
    members = strict_client.get(f"{API}/organizations/{org}").json()["members"]
    assert {m["email"]: m["role"] for m in members}["client@example.com"] == "VIEWER"
    assert strict_client.get(f"{API}/organizations/{org}/invitations").json() == []
    # A used link is dead, for everyone.
    assert accept(client, token).status_code == 404
    assert strict_client.app.state.s.accounts.open_invitation(token) is None  # type: ignore[attr-defined]


def test_invited_viewer_can_read_but_not_scan(
    strict_client: TestClient, mailer: CapturingMailer
) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "client@example.com")
    token = token_in(mailer)
    client = person(strict_client, "client@example.com")
    accept(client, token)
    headers = {"X-Organization-Id": org}
    assert client.get(f"{API}/scans", headers=headers).status_code == 200
    body = {"url": "https://example.com", "authorization_confirmed": True}
    assert client.post(f"{API}/scans", json=body, headers=headers).status_code == 403
    assert invite(client, org, "someone@example.com").status_code == 403


def test_the_link_only_works_for_the_invited_address(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "client@example.com")
    token = token_in(mailer)
    other = person(strict_client, "other@example.com")
    wrong = accept(other, token)
    assert wrong.status_code == 403
    assert "different email address" in wrong.json()["detail"]
    assert org not in [o["id"] for o in other.get(f"{API}/auth/me").json()["organizations"]]
    # The failed attempt did not use the invitation up.
    right = person(strict_client, "client@example.com")
    assert accept(right, token).status_code == 200


def test_an_unconfirmed_email_cannot_accept(strict_client: TestClient, mailer: CapturingMailer) -> None:
    invite(strict_client, org_of(strict_client), "client@example.com")
    token = token_in(mailer)
    client = person(strict_client, "client@example.com", verified=False)
    response = accept(client, token)
    assert response.status_code == 403
    assert "Confirm your email" in response.json()["detail"]


def test_accepting_needs_a_session(strict_client: TestClient, anon_client: TestClient, mailer: CapturingMailer) -> None:
    invite(strict_client, org_of(strict_client), "client@example.com")
    assert accept(anon_client, token_in(mailer)).status_code == 401


def test_expired_and_revoked_links_stop_working(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "old@example.com")
    expired = token_in(mailer)
    with strict_client.app.state.s.engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(update(InvitationRow).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    client = person(strict_client, "old@example.com")
    assert strict_client.get(f"{API}/invitations/preview", params={"token": expired}).status_code == 404
    assert accept(client, expired).status_code == 404

    created = invite(strict_client, org, "gone@example.com").json()
    revoked = token_in(mailer)
    assert strict_client.delete(f"{API}/organizations/{org}/invitations/{created['id']}").status_code == 204
    assert accept(person(strict_client, "gone@example.com"), revoked).status_code == 404
    assert strict_client.delete(f"{API}/organizations/{org}/invitations/{created['id']}").status_code == 404


def test_sending_again_replaces_the_earlier_link(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "client@example.com")
    first = token_in(mailer)
    invite(strict_client, org, "client@example.com", "MEMBER")
    second = token_in(mailer)
    assert first != second
    assert len(strict_client.get(f"{API}/organizations/{org}/invitations").json()) == 1
    client = person(strict_client, "client@example.com")
    assert accept(client, first).status_code == 404
    assert accept(client, second).status_code == 200
    mine = {o["id"]: o["role"] for o in client.get(f"{API}/auth/me").json()["organizations"]}
    assert mine[org] == "MEMBER"


def test_roles_limit_who_can_invite_and_what_they_can_grant(strict_client: TestClient) -> None:
    org = org_of(strict_client)
    for email, role in (("admin@example.com", "ADMIN"), ("member@example.com", "MEMBER")):
        person(strict_client, email)
        strict_client.post(f"{API}/organizations/{org}/members", json={"email": email, "role": role})
    admin = TestClient(strict_client.app)
    admin.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "correct-horse-battery-staple"})
    admin.headers["X-CSRF-Token"] = admin.cookies.get("ss_csrf") or ""
    member = TestClient(strict_client.app)
    member.post(f"{API}/auth/login", json={"email": "member@example.com", "password": "correct-horse-battery-staple"})
    member.headers["X-CSRF-Token"] = member.cookies.get("ss_csrf") or ""

    assert invite(member, org, "a@example.com").status_code == 403
    assert member.get(f"{API}/organizations/{org}/invitations").status_code == 403
    assert invite(admin, org, "b@example.com", "VIEWER").status_code == 201
    assert invite(admin, org, "c@example.com", "ADMIN").status_code == 403
    assert invite(admin, org, "d@example.com", "OWNER").status_code == 403
    owner_try = invite(strict_client, org, "e@example.com", "OWNER")
    assert owner_try.status_code == 400
    assert "owner" in owner_try.json()["detail"].lower()


def test_existing_members_and_bad_input_are_refused(strict_client: TestClient) -> None:
    org = org_of(strict_client)
    assert invite(strict_client, org, "alice@example.com").status_code == 409
    assert invite(strict_client, org, "not-an-email").status_code == 422
    assert (
        strict_client.post(f"{API}/organizations/{org}/invitations", json={"email": "a@b.co", "extra": 1}).status_code
        == 422
    )


def test_invitations_stay_inside_their_organization(strict_client: TestClient, bob_client: TestClient) -> None:
    alice_org, bob_org = org_of(strict_client), org_of(bob_client)
    created = invite(strict_client, alice_org, "client@example.com").json()
    assert bob_client.get(f"{API}/organizations/{alice_org}/invitations").status_code == 404
    assert invite(bob_client, alice_org, "x@example.com").status_code == 404
    # Bob cannot revoke Alice's invitation, not even by naming his own organization.
    assert bob_client.delete(f"{API}/organizations/{bob_org}/invitations/{created['id']}").status_code == 404
    assert len(strict_client.get(f"{API}/organizations/{alice_org}/invitations").json()) == 1


def test_sending_is_rate_limited(strict_client: TestClient) -> None:
    org = org_of(strict_client)
    for n in range(20):
        assert invite(strict_client, org, f"p{n}@example.com").status_code == 201
    assert invite(strict_client, org, "one-too-many@example.com").status_code == 429


def test_invitations_are_audited_without_secrets(strict_client: TestClient, mailer: CapturingMailer) -> None:
    org = org_of(strict_client)
    created = invite(strict_client, org, "client@example.com").json()
    token = token_in(mailer)
    accept(person(strict_client, "client@example.com"), token)
    invite(strict_client, org, "second@example.com")
    pending = [p for p in strict_client.get(f"{API}/organizations/{org}/invitations").json()]
    strict_client.delete(f"{API}/organizations/{org}/invitations/{pending[0]['id']}")
    with strict_client.app.state.s.engine.connect() as conn:  # type: ignore[attr-defined]
        rows = conn.execute(select(AuditEventRow)).all()
    kinds = {r.event_type for r in rows}
    assert {"org.invitation.created", "org.invitation.accepted", "org.invitation.revoked"} <= kinds
    assert token not in str([tuple(r) for r in rows])
    assert created["id"]


def test_only_a_digest_of_the_link_is_stored(strict_client: TestClient, mailer: CapturingMailer) -> None:
    invite(strict_client, org_of(strict_client), "client@example.com")
    token = token_in(mailer)
    with strict_client.app.state.s.engine.connect() as conn:  # type: ignore[attr-defined]
        stored = conn.execute(select(InvitationRow.token_hash)).scalars().all()
    assert stored and token not in stored


def test_old_invitations_are_cleaned_up(strict_client: TestClient) -> None:
    org = org_of(strict_client)
    invite(strict_client, org, "client@example.com")
    accounts = strict_client.app.state.s.accounts  # type: ignore[attr-defined]
    assert accounts.purge_old_invitations() == 0
    with strict_client.app.state.s.engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(update(InvitationRow).values(expires_at=datetime.now(UTC) - timedelta(days=31)))
    assert accounts.purge_old_invitations() == 1


def test_a_viewer_sees_only_their_own_entry_in_the_member_list(
    strict_client: TestClient, mailer: CapturingMailer
) -> None:
    """Clients are invited as viewers; they must not learn who else belongs to the workspace."""
    org = org_of(strict_client)
    invite(strict_client, org, "client-one@example.com")
    token_one = token_in(mailer)
    first = person(strict_client, "client-one@example.com")
    assert accept(first, token_one).status_code == 200
    invite(strict_client, org, "client-two@example.com")
    token_two = token_in(mailer)
    second = person(strict_client, "client-two@example.com")
    assert accept(second, token_two).status_code == 200

    seen = first.get(f"{API}/organizations/{org}")
    assert seen.status_code == 200
    assert [m["email"] for m in seen.json()["members"]] == ["client-one@example.com"]
    assert seen.json()["role"] == "VIEWER"
    # Nothing else in the response names the owner or the other client.
    assert "alice@example.com" not in seen.text
    assert "client-two@example.com" not in seen.text

    # Staff still see everyone.
    everyone = {m["email"] for m in strict_client.get(f"{API}/organizations/{org}").json()["members"]}
    assert everyone == {"alice@example.com", "client-one@example.com", "client-two@example.com"}

    # A member (not a viewer) keeps the full list.
    invite(strict_client, org, "colleague@example.com", "MEMBER")
    token_member = token_in(mailer)
    colleague = person(strict_client, "colleague@example.com")
    assert accept(colleague, token_member).status_code == 200
    assert len(colleague.get(f"{API}/organizations/{org}").json()["members"]) == 4
