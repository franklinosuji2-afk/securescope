from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.database.migrate import upgrade
from app.main import create_app


class MockHandler(BaseHTTPRequestHandler):
    """A tiny local target used by the integration tests (no internet required)."""

    server_version = "mock"
    sys_version = ""

    def log_message(self, *args: object) -> None:  # silence
        pass

    def _send(self, status: int, body: bytes, headers: dict[str, str | list[str]]) -> None:
        self.send_response(status)
        for key, value in headers.items():
            for item in value if isinstance(value, list) else [value]:
                self.send_header(key, item)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/plain":
            self._send(
                200,
                b"<html><title>hello</title></html>",
                {
                    "Content-Type": "text/html",
                    "Server": "nginx/1.18.0",
                    "X-Powered-By": "PHP/8.1.2",
                    "Set-Cookie": ["sid=SECRETVALUE123; Path=/", "pref=1; Path=/; HttpOnly; SameSite=Lax"],
                },
            )
        elif path == "/hardened":
            self._send(
                200,
                b"<html>ok</html>",
                {
                    "Content-Type": "text/html",
                    "Content-Security-Policy": "default-src 'self'",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "Permissions-Policy": "camera=()",
                },
            )
        elif path == "/listing":
            self._send(
                200,
                b"<html><head><title>Index of /files</title></head></html>",
                {"Content-Type": "text/html"},
            )
        elif path == "/redirect-same":
            self._send(302, b"", {"Location": "/plain"})
        elif path == "/redirect-off":
            self._send(302, b"", {"Location": "http://other.example.org/"})
        elif path == "/redirect-loop":
            self._send(302, b"", {"Location": "/redirect-loop"})
        elif path == "/slow":
            time.sleep(3)
            self._send(200, b"late", {"Content-Type": "text/plain"})
        elif path == "/big":
            body = b"A" * (3 * 1024 * 1024)
            self._send(200, body, {"Content-Type": "text/html"})
        else:
            self._send(404, b"not found", {"Content-Type": "text/plain"})


@pytest.fixture(scope="session")
def mock_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A freshly migrated database.

    SQLite by default. Set SECURESCOPE_TEST_DATABASE_URL to run the whole suite on PostgreSQL;
    the target schema is dropped and rebuilt through the real Alembic migrations.
    """
    url = os.environ.get("SECURESCOPE_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    if not url.startswith("sqlite"):
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
    upgrade(url)
    return url


@pytest.fixture
def make_settings(db_url: str):  # type: ignore[no-untyped-def]
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {"database_url": db_url, "cookie_secure": False}
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    return factory


PASSWORD = "correct-horse-battery-staple"


class CapturingMailer:
    """Collects outgoing mail so tests can follow verification and reset links."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def last_token(self) -> str:
        return self.sent[-1][2].rsplit("token=", 1)[1].strip()


def signup(client: TestClient, email: str, org: str | None = None) -> dict[str, Any]:
    """Registers a user; the client now carries the session cookie and the CSRF header."""
    payload: dict[str, Any] = {"email": email, "password": PASSWORD}
    if org:
        payload["organization_name"] = org
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("ss_csrf") or ""
    return response.json()  # type: ignore[no-any-return]


def trust_host(client: TestClient, host: str, organization_id: str | None = None) -> str:
    """Registers `host` as a verified target without running a real DNS/HTTP check.

    The verification logic itself is covered in test_targets.py; every other test only needs a
    verified target to exist. Returns the target id.
    """
    if organization_id is None:
        organization_id = client.get("/api/v1/auth/me").json()["organizations"][0]["id"]
    headers = {"X-Organization-Id": organization_id}
    created = client.post("/api/v1/targets", json={"hostname": host}, headers=headers)
    assert created.status_code == 201, created.text
    target_id: str = created.json()["id"]
    state = client.app.state.s  # type: ignore[attr-defined]
    state.targets.record_check(target_id, organization_id, method="dns_txt", error=None)
    return target_id


@pytest.fixture
def mailer() -> CapturingMailer:
    return CapturingMailer()


@pytest.fixture
def local_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    """Signed-in API client (alice) whose scanner may reach 127.0.0.1 (test-only switch)."""
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")  # the mock server's address
        yield client


@pytest.fixture
def strict_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    """Signed-in API client (alice) with production safety defaults."""
    with TestClient(create_app(make_settings(), mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        yield client


@pytest.fixture
def anon_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    """API client with no session."""
    with TestClient(create_app(make_settings(), mailer)) as client:
        yield client


@pytest.fixture
def bob_client(strict_client: TestClient) -> TestClient:
    """A second, independent session against the same app, belonging to another organization."""
    other = TestClient(strict_client.app)
    signup(other, "bob@example.com", "Bob Org")
    return other


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
