"""Account settings: details, signed-in devices, personal-data export. Every endpoint is for the caller only."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.tests.conftest import PASSWORD, signup

API = "/api/v1"


def second_device(app, email: str) -> TestClient:  # type: ignore[no-untyped-def]
    """Signs the same person in a second time, as a second browser would."""
    other = TestClient(app)
    response = other.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    other.headers["X-CSRF-Token"] = other.cookies.get("ss_csrf") or ""
    return other


def test_account_details(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        body = alice.get(f"{API}/account").json()
        assert body["email"] == "alice@example.com"
        assert body["status"] == "active"
        assert body["has_password"] is True
        assert body["created_at"]
        assert "password" not in json.dumps(body).lower().replace("has_password", "")
    with TestClient(create_app(make_settings(), mailer)) as anonymous:
        assert anonymous.get(f"{API}/account").status_code == 401


def test_sessions_list_and_sign_out_one_device(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        phone = second_device(app, "alice@example.com")
        sessions = alice.get(f"{API}/account/sessions").json()
        assert len(sessions) == 2
        assert [s["current"] for s in sessions].count(True) == 1
        assert not any("token" in key for s in sessions for key in s)
        other = next(s for s in sessions if not s["current"])
        current = next(s for s in sessions if s["current"])

        # The device in use cannot be revoked here; the other one can, and is signed out at once.
        assert alice.delete(f"{API}/account/sessions/{current['id']}").status_code == 400
        assert phone.get(f"{API}/auth/me").status_code == 200
        assert alice.delete(f"{API}/account/sessions/{other['id']}").status_code == 204
        assert phone.get(f"{API}/auth/me").status_code == 401
        assert len(alice.get(f"{API}/account/sessions").json()) == 1
        assert alice.get(f"{API}/auth/me").status_code == 200


def test_sign_out_all_other_devices(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        phone = second_device(app, "alice@example.com")
        laptop = second_device(app, "alice@example.com")
        assert alice.post(f"{API}/account/sessions/revoke-others").status_code == 204
        assert phone.get(f"{API}/auth/me").status_code == 401
        assert laptop.get(f"{API}/auth/me").status_code == 401
        assert alice.get(f"{API}/auth/me").status_code == 200


def test_nobody_can_see_or_end_another_persons_sessions(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as alice, TestClient(app) as bob:
        signup(alice, "alice@example.com", "Alice Org")
        signup(bob, "bob@example.com", "Bob Org")
        alice_session = alice.get(f"{API}/account/sessions").json()[0]["id"]
        bob_list = bob.get(f"{API}/account/sessions").json()
        assert len(bob_list) == 1
        assert alice_session not in [s["id"] for s in bob_list]
        # Bob cannot end Alice's session, and cannot tell whether the id exists.
        assert bob.delete(f"{API}/account/sessions/{alice_session}").status_code == 404
        assert bob.delete(f"{API}/account/sessions/not-a-real-id").status_code == 404
        assert alice.get(f"{API}/auth/me").status_code == 200
        # Bob signing out his other devices does not touch Alice.
        assert bob.post(f"{API}/account/sessions/revoke-others").status_code == 204
        assert alice.get(f"{API}/auth/me").status_code == 200


def test_session_endpoints_need_sign_in_and_csrf(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as anonymous:
        for method, path in [
            ("get", "/account/sessions"),
            ("post", "/account/sessions/revoke-others"),
            ("delete", "/account/sessions/abc"),
            ("get", "/account/export"),
        ]:
            assert getattr(anonymous, method)(f"{API}{path}").status_code == 401, path
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        del alice.headers["X-CSRF-Token"]
        assert alice.post(f"{API}/account/sessions/revoke-others").status_code in (401, 403)


def test_export_holds_only_the_callers_own_data(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as alice, TestClient(app) as bob:
        signup(alice, "alice@example.com", "Alice Org")
        signup(bob, "bob@example.com", "Bob Org")
        response = alice.get(f"{API}/account/export")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store"
        text = response.text
        data = response.json()
        assert data["account"]["email"] == "alice@example.com"
        assert [w["name"] for w in data["workspaces"]] == ["Alice Org"]
        # Nothing secret and nothing of Bob's.
        for forbidden in ("password_hash", "$argon2", "token", "bob@example.com", "Bob Org", "csrf"):
            assert forbidden not in text, forbidden
        assert PASSWORD not in text
        # The export itself is recorded in the account's audit trail.
        again = alice.get(f"{API}/account/export").json()
        assert any(e["event"] == "account.data_exported" for e in again["actions_recorded_in_the_audit_log"])
