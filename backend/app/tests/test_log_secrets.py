"""No credential, session value or one-time token may reach the application log."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.main import create_app
from app.services.mailer import ApiMailer
from app.tests.conftest import PASSWORD, signup

API = "/api/v1"


def test_secrets_never_appear_in_the_log(  # type: ignore[no-untyped-def]
    make_settings, mailer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    new_password = "a-brand-new-passphrase-9731"
    wrong_password = "definitely-the-wrong-passphrase-42"
    secrets: dict[str, str] = {
        "password": PASSWORD,
        "new password": new_password,
        "wrong password": wrong_password,
    }

    with TestClient(create_app(make_settings(), mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        secrets["session cookie"] = client.cookies.get("ss_session") or ""
        secrets["csrf cookie"] = client.cookies.get("ss_csrf") or ""

        created = client.post(f"{API}/api-tokens", json={"name": "CI"})
        assert created.status_code == 201, created.text
        body: dict[str, Any] = created.json()
        api_token = str(body.get("token") or body.get("secret") or "")
        assert api_token, "the create response is expected to show the token once"
        secrets["api token"] = api_token
        client.get(f"{API}/targets", headers={"Authorization": f"Bearer {api_token}"})

        with TestClient(create_app(make_settings(), mailer)) as visitor:
            bad = visitor.post(
                f"{API}/auth/login", json={"email": "alice@example.com", "password": wrong_password}
            )
            assert bad.status_code == 401
            visitor.post(f"{API}/auth/forgot-password", json={"email": "alice@example.com"})
            reset_token = mailer.last_token()
            secrets["reset token"] = reset_token
            done = visitor.post(
                f"{API}/auth/reset-password", json={"token": reset_token, "password": new_password}
            )
            assert done.status_code in (200, 204), done.text

    formatter = JsonFormatter()
    rendered = "\n".join(formatter.format(record) for record in caplog.records)
    for name, value in secrets.items():
        assert value, f"{name} was empty, so the check would prove nothing"
        assert value not in rendered, f"{name} appears in the application log"


@pytest.mark.parametrize("status", [200, 500])
def test_mail_logs_hold_no_key_link_or_recipient(status: int, caplog: pytest.LogCaptureFixture) -> None:
    """The real mail path logs only the provider and status, never the key, the body or the address."""
    caplog.set_level(logging.DEBUG)
    api_key = "mail-api-key-should-never-be-logged"
    body = "Reset your password: https://example.org/#/reset-password?token=one-time-secret-value"
    settings = Settings(
        database_url="sqlite://",
        mail_provider="brevo",
        mail_api_key=api_key,
        mail_from_email="no-reply@example.org",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    ApiMailer(settings, transport).send("private.person@example.com", "Reset", body)

    rendered = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "mail" in rendered, "expected a mail log line"
    for secret in (api_key, "one-time-secret-value", "private.person@example.com"):
        assert secret not in rendered
