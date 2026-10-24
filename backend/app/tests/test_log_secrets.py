"""Secrets must never reach the application log.

Runs the sensitive flows (sign-up, failed and successful sign-in, password reset, API token and
webhook creation, a token-authenticated call) with every logger at DEBUG, formats each record the way
production does, and checks that no password, session cookie, CSRF value, reset token, API token or
signing secret appears anywhere in the output.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app import main as main_module
from app.main import create_app
from app.tests.conftest import PASSWORD, CapturingMailer, signup

NEW_PASSWORD = "a-completely-different-passphrase-9"
WRONG_PASSWORD = "definitely-not-the-password-123"


class Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self._fmt = JsonFormatter()

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self._fmt.format(record))


def test_no_secret_reaches_the_log(
    make_settings: Any, mailer: CapturingMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = Collect()
    root = logging.getLogger()
    old_level = root.level
    old_handlers = list(root.handlers)

    def configure(level: str = "INFO") -> None:
        # The app installs its own handler on start-up; keep ours next to it so we see every record.
        real_configure(level)
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

    real_configure = main_module.configure_logging
    monkeypatch.setattr(main_module, "configure_logging", configure)
    secrets: dict[str, str] = {}
    try:
        with TestClient(create_app(make_settings(allow_private_targets=True), mailer)) as client:
            signup(client, "alice@example.com", "Alice Org")
            secrets["session cookie"] = client.cookies.get("ss_session") or ""
            secrets["csrf value"] = client.cookies.get("ss_csrf") or ""

            token = client.post("/api/v1/api-tokens", json={"name": "CI"})
            if token.status_code == 201:
                secrets["api token"] = token.json()["token"]
                client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {secrets['api token']}"})

            hook = client.post("/api/v1/webhooks", json={"url": "https://example.com/hook"})
            if hook.status_code == 201:
                secrets["webhook secret"] = hook.json()["signing_secret"]

            with TestClient(create_app(make_settings(), mailer)) as other:
                other.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": WRONG_PASSWORD})
                other.post("/api/v1/auth/forgot-password", json={"email": "alice@example.com"})
                secrets["reset token"] = mailer.last_token()
                other.post(
                    "/api/v1/auth/reset-password", json={"token": secrets["reset token"], "password": NEW_PASSWORD}
                )
                other.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": NEW_PASSWORD})
    finally:
        root.handlers[:] = old_handlers
        root.setLevel(old_level)

    secrets.update({"password": PASSWORD, "new password": NEW_PASSWORD, "wrong password": WRONG_PASSWORD})
    assert handler.lines, "the test captured no log output at all"
    output = "\n".join(handler.lines)
    for name, value in secrets.items():
        assert len(value) >= 8, f"{name} was not captured, so the test would prove nothing"
        assert value not in output, f"{name} appears in the application log"
