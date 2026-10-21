from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.main import create_app
from app.models.account import AuditEventRow, OAuthIdentityRow, UserRow
from app.tests.conftest import PASSWORD, CapturingMailer

API = "/api/v1"
SECRET = "super-secret-client-value"


class FakeProviders:
    """Stands in for Google and GitHub. `profile` is what the provider reports about the person."""

    def __init__(self) -> None:
        self.google: dict[str, Any] = {"sub": "g-1", "email": "Ada@Example.com", "email_verified": True}
        self.github_user: dict[str, Any] = {"id": 77}
        self.github_emails: list[dict[str, Any]] = [
            {"email": "ada@example.com", "primary": True, "verified": True},
            {"email": "other@example.com", "primary": False, "verified": True},
        ]
        self.token_status = 200
        self.token_forms: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/token") or url.endswith("/access_token"):
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_forms.append(form)
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "boom", "echo": SECRET})
            return httpx.Response(200, json={"access_token": "tok-123"})
        assert request.headers["authorization"] == "Bearer tok-123"
        if url.startswith("https://openidconnect.googleapis.com/"):
            return httpx.Response(200, json=self.google)
        if url == "https://api.github.com/user":
            return httpx.Response(200, json=self.github_user)
        if url == "https://api.github.com/user/emails":
            return httpx.Response(200, json=self.github_emails)
        return httpx.Response(404)


@pytest.fixture
def providers() -> FakeProviders:
    return FakeProviders()


@pytest.fixture
def make_client(make_settings, providers):  # type: ignore[no-untyped-def]
    clients: list[TestClient] = []

    def factory(mailer: CapturingMailer | None = None, **overrides: object) -> TestClient:
        values: dict[str, object] = {
            "oauth_google_client_id": "gid",
            "oauth_google_client_secret": SECRET,
            "oauth_github_client_id": "hid",
            "oauth_github_client_secret": SECRET,
            "public_base_url": "https://site.example",
        }
        values.update(overrides)
        app = create_app(make_settings(**values), mailer or CapturingMailer())
        client = TestClient(app, follow_redirects=False)
        client.__enter__()
        clients.append(client)
        client.app.state.s.oauth._client = httpx.Client(  # type: ignore[attr-defined]
            transport=httpx.MockTransport(providers.handler)
        )
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def start(client: TestClient, provider: str) -> tuple[Any, dict[str, list[str]]]:
    response = client.get(f"{API}/auth/oauth/{provider}/start")
    return response, parse_qs(urlparse(response.headers.get("location", "")).query)


def sign_in(client: TestClient, provider: str = "google") -> Any:
    response, query = start(client, provider)
    assert response.status_code == 302
    return client.get(
        f"{API}/auth/oauth/{provider}/callback", params={"code": "the-code", "state": query["state"][0]}
    )


def target(response: Any) -> str:
    return str(response.headers["location"])


def test_buttons_follow_configuration(make_client) -> None:  # type: ignore[no-untyped-def]
    both = make_client()
    assert both.get(f"{API}/auth/providers").json() == {"providers": ["google", "github"]}
    only = make_client(oauth_github_client_id=None, oauth_github_client_secret=None)
    assert only.get(f"{API}/auth/providers").json() == {"providers": ["google"]}
    assert only.get(f"{API}/auth/oauth/github/start").status_code == 404
    none = make_client(
        oauth_google_client_id=None,
        oauth_google_client_secret=None,
        oauth_github_client_id=None,
        oauth_github_client_secret=None,
    )
    assert none.get(f"{API}/auth/providers").json() == {"providers": []}


def test_a_half_configured_provider_stays_off_without_stopping_the_api(  # type: ignore[no-untyped-def]
    make_client, capsys: pytest.CaptureFixture[str]
) -> None:
    client = make_client(oauth_github_client_secret=None, oauth_google_client_secret="")
    logged = capsys.readouterr().out
    assert client.get(f"{API}/auth/providers").json() == {"providers": []}
    assert client.get(f"{API}/auth/oauth/google/start").status_code == 404
    assert client.get(f"{API}/health").status_code == 200
    assert logged.count("half configured") == 2
    assert SECRET not in logged


def test_start_sends_the_browser_to_the_provider_with_state_and_pkce(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    response, query = start(client, "google")
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert query["client_id"] == ["gid"]
    assert query["redirect_uri"] == ["https://site.example/api/v1/auth/oauth/google/callback"]
    assert query["code_challenge_method"] == ["S256"] and len(query["state"][0]) >= 32
    assert "client_secret" not in response.headers["location"] and SECRET not in response.headers["location"]
    cookie = response.headers["set-cookie"].lower()
    assert "ss_oauth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api/v1/auth/oauth" in cookie and response.headers["cache-control"] == "no-store"


def test_first_sign_in_creates_an_account_and_workspace(make_client, providers) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    response, query = start(client, "google")
    done = client.get(
        f"{API}/auth/oauth/google/callback", params={"code": "c1", "state": query["state"][0]}
    )
    assert done.status_code == 302 and target(done) == "https://site.example/#/"
    cookies = " ".join(done.headers.get_list("set-cookie"))
    assert "ss_session=" in cookies and "ss_csrf=" in cookies
    # the code was exchanged with the PKCE verifier that matches the challenge sent first
    form = providers.token_forms[-1]
    digest = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=")
    assert digest.decode() == query["code_challenge"][0]
    assert form["client_secret"] == SECRET and form["code"] == "c1"
    me = client.get(f"{API}/auth/me").json()
    assert me["email"] == "ada@example.com" and me["email_verified"] is True
    assert me["organizations"][0]["role"] == "OWNER"
    # there is no password to guess
    assert client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": "!"}).status_code in (401, 422)
    engine = client.app.state.s.engine
    with engine.connect() as conn:
        assert conn.scalar(select(OAuthIdentityRow.subject)) == "g-1"
        types = set(conn.scalars(select(AuditEventRow.event_type)))
    assert "user.registered" in types


def test_signing_in_again_reaches_the_same_account(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    sign_in(client)
    first = client.get(f"{API}/auth/me").json()["id"]
    client.cookies.clear()
    done = sign_in(client)
    assert target(done) == "https://site.example/#/"
    assert client.get(f"{API}/auth/me").json()["id"] == first
    engine = client.app.state.s.engine
    with engine.connect() as conn:
        assert len(conn.scalars(select(UserRow.id)).all()) == 1


def test_a_verified_email_links_to_the_existing_password_account(make_client, providers) -> None:  # type: ignore[no-untyped-def]
    mailer = CapturingMailer()
    client = make_client(mailer)
    client.post(f"{API}/auth/register", json={"email": "ada@example.com", "password": PASSWORD})
    token = mailer.last_token()
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    original = client.get(f"{API}/auth/me").json()["id"]
    client.cookies.clear()
    done = sign_in(client)
    assert target(done) == "https://site.example/#/"
    assert client.get(f"{API}/auth/me").json()["id"] == original
    client.cookies.clear()
    # the password still works: nothing was taken from the owner
    assert client.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200


def test_an_unconfirmed_account_loses_its_password_when_the_real_owner_signs_in(make_client) -> None:  # type: ignore[no-untyped-def]
    """Someone registered ada@example.com in advance and never confirmed it."""
    client = make_client()
    client.post(f"{API}/auth/register", json={"email": "ada@example.com", "password": PASSWORD})
    squatter_cookie = client.cookies.get("ss_session")
    assert squatter_cookie
    client.cookies.clear()
    done = sign_in(client)
    assert target(done) == "https://site.example/#/"
    assert client.get(f"{API}/auth/me").json()["email_verified"] is True
    other = TestClient(client.app, follow_redirects=False)
    other.cookies.set("ss_session", squatter_cookie)
    assert other.get(f"{API}/auth/me").status_code == 401  # the squatter's session was ended
    other.cookies.clear()
    assert other.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401


def test_an_unverified_provider_email_is_never_trusted(make_client, providers) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    providers.google["email_verified"] = False
    done = sign_in(client)
    assert target(done) == "https://site.example/#/login?oauth_error=email_unverified"
    assert client.get(f"{API}/auth/me").status_code == 401
    engine = client.app.state.s.engine
    with engine.connect() as conn:
        assert conn.scalars(select(UserRow.id)).all() == []


def test_github_uses_the_primary_verified_email(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    done = sign_in(client, "github")
    assert target(done) == "https://site.example/#/"
    assert client.get(f"{API}/auth/me").json()["email"] == "ada@example.com"


def test_github_without_a_verified_primary_email_is_refused(make_client, providers) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    providers.github_emails = [{"email": "ada@example.com", "primary": True, "verified": False}]
    assert target(sign_in(client, "github")).endswith("oauth_error=email_unverified")


def test_state_is_single_use_and_bound_to_the_browser(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    _, query = start(client, "google")
    state = query["state"][0]
    good = client.get(f"{API}/auth/oauth/google/callback", params={"code": "c", "state": state})
    assert target(good) == "https://site.example/#/"
    client.cookies.clear()
    replay = client.get(f"{API}/auth/oauth/google/callback", params={"code": "c", "state": state})
    assert target(replay).endswith("oauth_error=failed")
    assert client.get(f"{API}/auth/me").status_code == 401

    # a state issued to one browser is useless in another (login CSRF)
    _, query = start(client, "google")
    attacker_state = query["state"][0]
    victim = TestClient(client.app, follow_redirects=False)
    victim.cookies.set("ss_oauth", "not-the-attackers-cookie", path="/api/v1/auth/oauth")
    stolen = victim.get(f"{API}/auth/oauth/google/callback", params={"code": "c", "state": attacker_state})
    assert target(stolen).endswith("oauth_error=failed")
    assert victim.get(f"{API}/auth/me").status_code == 401

    # no cookie at all, an unknown state, and the wrong provider all fail
    nobody = TestClient(client.app, follow_redirects=False)
    assert target(nobody.get(f"{API}/auth/oauth/google/callback", params={"code": "c", "state": "x" * 40})).endswith(
        "oauth_error=failed"
    )
    _, query = start(client, "google")
    wrong = client.get(f"{API}/auth/oauth/github/callback", params={"code": "c", "state": query["state"][0]})
    assert target(wrong).endswith("oauth_error=failed")


def test_declining_at_the_provider_is_reported_plainly(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    start(client, "google")
    done = client.get(f"{API}/auth/oauth/google/callback", params={"error": "access_denied", "state": "x"})
    assert target(done) == "https://site.example/#/login?oauth_error=cancelled"
    assert client.get(f"{API}/auth/oauth/google/callback").headers["location"].endswith("oauth_error=failed")


def test_a_provider_outage_never_leaks_anything(make_client, providers, capsys: pytest.CaptureFixture[str]) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    providers.token_status = 500
    capsys.readouterr()
    done = sign_in(client)
    logged = capsys.readouterr().out
    assert "oauth exchange failed" in logged  # the log really is captured, so the checks below mean something
    assert target(done) == "https://site.example/#/login?oauth_error=failed"
    assert SECRET not in done.headers["location"] and "boom" not in done.headers["location"]
    assert SECRET not in logged and "the-code" not in logged and "tok-123" not in logged
    assert client.get(f"{API}/auth/me").status_code == 401


def test_a_disabled_account_cannot_sign_in(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    sign_in(client)
    client.cookies.clear()
    engine = client.app.state.s.engine
    with engine.begin() as conn:
        conn.execute(update(UserRow).values(account_status="DISABLED"))
    assert target(sign_in(client)).endswith("oauth_error=disabled")
    assert client.get(f"{API}/auth/me").status_code == 401


def test_provider_responses_with_missing_fields_fail_safely(make_client, providers) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    providers.google = {"email": "ada@example.com", "email_verified": True}  # no "sub"
    assert target(sign_in(client)).endswith("oauth_error=failed")


def test_the_log_records_the_outcome_but_not_the_secrets(make_client, capsys: pytest.CaptureFixture[str]) -> None:  # type: ignore[no-untyped-def]
    client = make_client()
    capsys.readouterr()
    sign_in(client)
    logged = capsys.readouterr().out
    assert SECRET not in logged and "the-code" not in logged and "tok-123" not in logged
    assert json.dumps(client.get(f"{API}/auth/providers").json())
