from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.tests.conftest import PASSWORD, CapturingMailer, signup

API = "/api/v1"


def test_register_sets_hardened_cookies_and_never_returns_secrets(anon_client: TestClient) -> None:
    response = anon_client.post(
        f"{API}/auth/register", json={"email": "New@Example.com", "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"  # normalised
    assert body["organizations"][0]["role"] == "OWNER"
    assert "password" not in response.text and "hash" not in response.text
    cookies = {c.split("=")[0]: c for c in response.headers.get_list("set-cookie")}
    session = cookies["ss_session"].lower()
    assert "httponly" in session and "samesite=lax" in session
    assert "httponly" not in cookies["ss_csrf"].lower()  # the SPA must be able to read it


def test_session_cookie_is_secure_by_default(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    settings = make_settings(cookie_secure=True)
    with TestClient(create_app(settings, mailer)) as client:
        response = client.post(f"{API}/auth/register", json={"email": "s@example.com", "password": PASSWORD})
        assert "secure" in response.headers["set-cookie"].lower()


def test_password_is_stored_as_argon2id(strict_client: TestClient) -> None:
    from app.models.account import UserRow

    engine = strict_client.app.state.s.engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        stored = conn.scalar(select(UserRow.password_hash))
    assert stored.startswith("$argon2id$") and PASSWORD not in stored


def test_weak_and_malformed_registrations_are_rejected(anon_client: TestClient) -> None:
    assert (
        anon_client.post(f"{API}/auth/register", json={"email": "a@b.co", "password": "short"}).status_code
        == 422
    )
    assert (
        anon_client.post(
            f"{API}/auth/register", json={"email": "not-an-email", "password": PASSWORD}
        ).status_code
        == 422
    )
    extra = {"email": "a@b.co", "password": PASSWORD, "is_admin": True}
    assert anon_client.post(f"{API}/auth/register", json=extra).status_code == 422  # unknown fields refused


def test_duplicate_email_is_rejected_case_insensitively(strict_client: TestClient) -> None:
    other = TestClient(strict_client.app)
    response = other.post(f"{API}/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert response.status_code == 409


def test_me_requires_a_session(anon_client: TestClient) -> None:
    assert anon_client.get(f"{API}/auth/me").status_code == 401


def test_login_logout_and_revocation(strict_client: TestClient) -> None:
    fresh = TestClient(strict_client.app)
    assert (
        fresh.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code
        == 200
    )
    fresh.headers["X-CSRF-Token"] = fresh.cookies.get("ss_csrf") or ""
    assert fresh.get(f"{API}/auth/me").status_code == 200
    assert fresh.post(f"{API}/auth/logout").status_code == 204
    assert fresh.get(f"{API}/auth/me").status_code == 401
    # the original session of the same user is unaffected
    assert strict_client.get(f"{API}/auth/me").status_code == 200


def test_replaying_a_revoked_cookie_fails(strict_client: TestClient) -> None:
    stolen = strict_client.cookies.get("ss_session") or ""
    assert strict_client.post(f"{API}/auth/logout").status_code == 204
    replay = TestClient(strict_client.app, cookies={"ss_session": stolen})
    assert replay.get(f"{API}/auth/me").status_code == 401


def test_login_errors_do_not_reveal_whether_the_account_exists(anon_client: TestClient) -> None:
    signup(anon_client, "real@example.com")
    fresh = TestClient(anon_client.app)
    wrong = fresh.post(
        f"{API}/auth/login", json={"email": "real@example.com", "password": "wrong-password-1"}
    )
    unknown = fresh.post(
        f"{API}/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-1"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_rate_limited_per_email(anon_client: TestClient) -> None:
    signup(anon_client, "target@example.com")
    attacker = TestClient(anon_client.app)
    for _ in range(5):
        r = attacker.post(
            f"{API}/auth/login", json={"email": "target@example.com", "password": "guess-guess-guess"}
        )
        assert r.status_code == 401
    blocked = attacker.post(f"{API}/auth/login", json={"email": "target@example.com", "password": PASSWORD})
    assert blocked.status_code == 429  # even the right password is refused while locked out


def test_registration_is_rate_limited(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    with TestClient(create_app(make_settings(registrations_per_ip_per_hour=2), mailer)) as client:
        codes = [
            client.post(
                f"{API}/auth/register", json={"email": f"u{i}@example.com", "password": PASSWORD}
            ).status_code
            for i in range(3)
        ]
    assert codes == [201, 201, 429]


def test_csrf_token_is_required_for_unsafe_methods(strict_client: TestClient) -> None:
    token = strict_client.headers.pop("X-CSRF-Token")
    body = {"url": "https://example.org", "authorization_confirmed": True}
    assert strict_client.post(f"{API}/scans", json=body).status_code == 403
    strict_client.headers["X-CSRF-Token"] = "wrong"
    assert strict_client.post(f"{API}/scans", json=body).status_code == 403
    strict_client.headers["X-CSRF-Token"] = token
    assert strict_client.get(f"{API}/scans").status_code == 200  # safe methods need no token


def test_csrf_token_of_another_session_is_rejected(strict_client: TestClient, bob_client: TestClient) -> None:
    strict_client.headers["X-CSRF-Token"] = bob_client.headers["X-CSRF-Token"]
    assert strict_client.post(f"{API}/auth/logout").status_code == 403


def test_cross_origin_unsafe_requests_are_rejected(strict_client: TestClient) -> None:
    response = strict_client.post(f"{API}/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert strict_client.get(f"{API}/auth/me").status_code == 200  # session untouched
    ok = strict_client.post(f"{API}/auth/refresh", headers={"Origin": "http://localhost:8080"})
    assert ok.status_code == 200


def test_refresh_rotates_the_session(strict_client: TestClient) -> None:
    old_cookie = strict_client.cookies.get("ss_session") or ""
    response = strict_client.post(f"{API}/auth/refresh")
    assert response.status_code == 200
    new_cookie = strict_client.cookies.get("ss_session")
    assert new_cookie != old_cookie
    strict_client.headers["X-CSRF-Token"] = strict_client.cookies.get("ss_csrf") or ""
    replay = TestClient(strict_client.app, cookies={"ss_session": old_cookie})
    assert replay.get(f"{API}/auth/me").status_code == 401


def test_expired_sessions_are_not_accepted(strict_client: TestClient) -> None:
    from datetime import timedelta

    state = strict_client.app.state.s  # type: ignore[attr-defined]
    user = state.accounts.get_user_by_email("alice@example.com")
    state.accounts.create_session(user.id, "expired-token", "csrf", timedelta(seconds=-5))
    assert state.accounts.get_session("expired-token") is None


def test_password_reset_flow(anon_client: TestClient, mailer: CapturingMailer) -> None:
    signup(anon_client, "forgetful@example.com")
    forgot = TestClient(anon_client.app)
    known = forgot.post(f"{API}/auth/forgot-password", json={"email": "forgetful@example.com"})
    token = mailer.last_token()
    unknown = forgot.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert len(mailer.sent) == 2  # registration verification mail + one reset mail (none for unknown)

    new_password = "an-entirely-new-passphrase"
    assert (
        forgot.post(f"{API}/auth/reset-password", json={"token": token, "password": new_password}).status_code
        == 200
    )
    assert (
        forgot.post(f"{API}/auth/reset-password", json={"token": token, "password": new_password}).status_code
        == 400
    )  # single use
    assert anon_client.get(f"{API}/auth/me").status_code == 401  # old session ended
    assert (
        forgot.post(
            f"{API}/auth/login", json={"email": "forgetful@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        forgot.post(
            f"{API}/auth/login", json={"email": "forgetful@example.com", "password": new_password}
        ).status_code
        == 200
    )


def test_invalid_reset_and_verification_tokens(anon_client: TestClient) -> None:
    bad = {"token": "x" * 30, "password": PASSWORD}
    assert anon_client.post(f"{API}/auth/reset-password", json=bad).status_code == 400
    assert anon_client.post(f"{API}/auth/verify-email", json={"token": "y" * 30}).status_code == 400


def test_email_verification(anon_client: TestClient, mailer: CapturingMailer) -> None:
    created = signup(anon_client, "verify@example.com")
    assert created["email_verified"] is False
    token = mailer.last_token()
    assert anon_client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert anon_client.get(f"{API}/auth/me").json()["email_verified"] is True
    assert anon_client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400


def test_security_relevant_actions_are_audited(strict_client: TestClient) -> None:
    fresh = TestClient(strict_client.app)
    fresh.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": "wrong-password-1"})
    fresh.post(f"{API}/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    strict_client.post(f"{API}/organizations", json={"name": "Second"})
    types = strict_client.app.state.s.audit.all_event_types()  # type: ignore[attr-defined]
    for expected in ("user.registered", "auth.login.failed", "auth.login.success", "org.created"):
        assert expected in types


def test_request_ids_are_echoed_or_replaced(strict_client: TestClient) -> None:
    good = strict_client.get(f"{API}/health", headers={"X-Request-ID": "abc-12345678"})
    assert good.headers["x-request-id"] == "abc-12345678"
    evil = strict_client.get(f"{API}/health", headers={"X-Request-ID": "x\r\ninjected: 1"})
    assert evil.headers["x-request-id"] != "x" and "injected" not in evil.headers


def test_resend_verification_sends_a_working_link_and_is_limited(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.tests.conftest import signup

    with TestClient(create_app(make_settings(), mailer)) as client:
        assert client.post("/api/v1/auth/resend-verification").status_code == 401
        signup(client, "carol@example.com", "Carol Org")
        sent_at_signup = len(mailer.sent)
        assert client.post("/api/v1/auth/resend-verification").status_code == 202
        assert len(mailer.sent) == sent_at_signup + 1
        to, _subject, _body = mailer.sent[-1]
        assert to == "carol@example.com"
        token = mailer.last_token()
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
        assert client.get("/api/v1/auth/me").json()["email_verified"] is True
        # Once confirmed, nothing more is sent.
        before = len(mailer.sent)
        assert client.post("/api/v1/auth/resend-verification").status_code == 202
        assert len(mailer.sent) == before


def test_resend_verification_is_rate_limited(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.tests.conftest import signup

    with TestClient(create_app(make_settings(), mailer)) as client:
        signup(client, "dan@example.com", "Dan Org")
        codes = [client.post("/api/v1/auth/resend-verification").status_code for _ in range(5)]
        assert codes == [202, 202, 202, 429, 429]
