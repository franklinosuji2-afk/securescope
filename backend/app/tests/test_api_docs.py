from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_api_docs_are_off_by_default(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404


def test_api_docs_can_be_switched_on_for_local_development(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(api_docs_enabled=True), mailer)) as client:
        assert client.get("/api/docs").status_code == 200
        assert client.get("/api/openapi.json").json()["info"]["title"] == "SecureScope API"
