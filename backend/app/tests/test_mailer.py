"""The production mailer: provider requests, failure handling and secrets."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.services.mailer import ApiMailer, LogMailer, build_mailer
from app.tests.conftest import signup

KEY = "test-key-do-not-leak"


def mail_settings(provider: str, **extra: object) -> Settings:
    return Settings(
        database_url="sqlite://",
        mail_provider=provider,
        mail_api_key=KEY,
        mail_from_email="no-reply@example.org",
        **extra,  # type: ignore[arg-type]
    )


def capture(status: int = 200) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"ok": status < 400})

    return httpx.MockTransport(handler), seen


def test_log_is_the_default_and_needs_no_credentials() -> None:
    assert isinstance(build_mailer(Settings(database_url="sqlite://")), LogMailer)


@pytest.mark.parametrize("missing", ["mail_api_key", "mail_from_email"])
def test_a_real_provider_requires_a_key_and_a_sender(missing: str) -> None:
    values: dict[str, object] = {
        "database_url": "sqlite://",
        "mail_provider": "brevo",
        "mail_api_key": KEY,
        "mail_from_email": "a@example.org",
    }
    values.pop(missing)
    with pytest.raises(ValidationError):
        Settings(**values)  # type: ignore[arg-type]


def test_brevo_request_shape() -> None:
    transport, seen = capture()
    ApiMailer(mail_settings("brevo"), transport).send("user@example.com", "Hello", "Open this link: x")
    request = seen[0]
    assert str(request.url) == "https://api.brevo.com/v3/smtp/email"
    assert request.headers["api-key"] == KEY
    body = json.loads(request.content)
    assert body["to"] == [{"email": "user@example.com"}]
    assert body["sender"]["email"] == "no-reply@example.org"
    assert body["subject"] == "Hello" and body["textContent"] == "Open this link: x"


def test_resend_request_shape() -> None:
    transport, seen = capture()
    ApiMailer(mail_settings("resend", mail_from_name="SecureScope"), transport).send(
        "u@example.com", "Hi", "text"
    )
    request = seen[0]
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["from"] == "SecureScope <no-reply@example.org>" and body["to"] == ["u@example.com"]


@pytest.mark.parametrize("failure", ["status", "network"])
def test_a_provider_failure_never_raises_and_never_logs_secrets(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    if failure == "status":
        transport, _ = capture(500)
    else:

        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        transport = httpx.MockTransport(boom)
    caplog.set_level(logging.INFO, logger="securescope.mail")
    ApiMailer(mail_settings("brevo"), transport).send("u@example.com", "Hi", "secret-link?token=abc123")
    logged = " ".join(repr(r.__dict__) for r in caplog.records)
    assert "mail send failed" in logged
    for secret in (KEY, "abc123", "secret-link"):
        assert secret not in logged


def test_registration_sends_the_verification_email_and_survives_a_provider_outage(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from app.database.migrate import upgrade

    url = f"sqlite:///{tmp_path / 'm.db'}"
    upgrade(url)
    transport, seen = capture()
    settings = Settings(
        database_url=url,
        cookie_secure=False,
        mail_provider="brevo",
        mail_api_key=KEY,
        mail_from_email="no-reply@example.org",
        public_base_url="https://app.example.org",
    )
    with TestClient(create_app(settings, ApiMailer(settings, transport))) as client:
        signup(client, "new@example.com")
    sent = json.loads(seen[0].content)
    assert sent["to"] == [{"email": "new@example.com"}]
    assert "https://app.example.org/verify-email?token=" in sent["textContent"]

    down, _ = capture(503)
    url2 = f"sqlite:///{tmp_path / 'm2.db'}"
    upgrade(url2)
    settings2 = settings.model_copy(update={"database_url": url2})
    with TestClient(create_app(settings2, ApiMailer(settings2, down))) as client:
        signup(client, "other@example.com")  # registration still succeeds
