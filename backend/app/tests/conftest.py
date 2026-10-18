from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
        values: dict[str, object] = {"database_url": db_url}
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def local_client(make_settings):  # type: ignore[no-untyped-def]
    """API client whose scanner may reach 127.0.0.1 (test-only switch)."""
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0)
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def strict_client(make_settings):  # type: ignore[no-untyped-def]
    """API client with production safety defaults."""
    with TestClient(create_app(make_settings())) as client:
        yield client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
