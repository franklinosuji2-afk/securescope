"""Error responses must not reveal internals, secrets or the exception that caused them."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

MARKER = "db-password-hunter2-and-/srv/app/secret_path.py"


def test_an_unhandled_error_has_a_generic_body(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError(MARKER)

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/api/v1/boom")
    assert response.status_code == 500
    text = response.text + str(dict(response.headers))
    for forbidden in (MARKER, "hunter2", "secret_path", "Traceback", "RuntimeError", 'File "'):
        assert forbidden not in text, forbidden


def test_a_validation_error_names_the_field_but_not_the_value(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    with TestClient(app) as c:
        response = c.post("/api/v1/auth/login", json={"email": "not-an-email-value", "password": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["detail"] and all(set(e) == {"loc", "msg", "type"} for e in body["detail"])
    assert "not-an-email-value" not in response.text


def test_a_rejected_new_password_is_not_echoed_back(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)
    weak = "short-pw"
    with TestClient(app) as c:
        response = c.post("/api/v1/auth/register", json={"email": "a@example.com", "password": weak})
    assert response.status_code == 422
    assert weak not in response.text
