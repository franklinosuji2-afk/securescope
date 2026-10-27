"""App Scanning pilot allow-list: with the feature switched on, only the listed workspaces may use it.

The list is an extra gate on top of the plans. It changes no plan value and nothing in Web Scanning. A workspace that
is not listed gets exactly the answer it gets while the feature is off, so the feature does not exist for it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.tests.conftest import signup
from app.tests.test_appscan_ci_tokens import APP, SUBMIT, doc, make_token, new_project
from app.tests.test_integrations import bare, bearer
from app.tests.test_tenancy import org_of

API = "/api/v1"
NOT_FOUND = {"detail": "Not found."}


def client_for(make_settings: Any, mailer: Any, allowed: list[str] | None) -> TestClient:
    settings = make_settings(app_scanning_enabled=True, app_scanning_allowed_orgs=allowed)
    return TestClient(create_app(settings, mailer))


def test_without_a_list_every_workspace_may_use_the_feature(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with client_for(make_settings, mailer, None) as client:
        signup(client, "owner@example.com", "Org")
        assert client.get(f"{APP}/overview").status_code == 200
        assert client.post(f"{APP}/projects", json={"name": "svc"}).status_code == 201


def test_a_listed_workspace_has_the_whole_feature(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with client_for(make_settings, mailer, None) as first:
        signup(first, "owner@example.com", "Org")
        org = org_of(first)
    with client_for(make_settings, mailer, [org]) as client:
        client.post(
            f"{API}/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        client.headers["X-CSRF-Token"] = client.cookies.get("ss_csrf") or ""
        assert client.get(f"{APP}/overview").status_code == 200
        pid = new_project(client)
        token = make_token(client, "app")
        assert token.status_code == 201, token.text
        sent = bare(client).post(
            SUBMIT,
            content=json.dumps(doc(pid)),
            headers={
                **bearer(token.json()["token"]),
                "Idempotency-Key": "k1",
                "Content-Type": "application/json",
            },
        )
        assert sent.status_code == 201, sent.text


@pytest.mark.parametrize("allowed", [[], ["some-other-workspace"]])
def test_a_workspace_that_is_not_listed_meets_a_feature_that_does_not_exist(  # type: ignore[no-untyped-def]
    make_settings, mailer, allowed
) -> None:
    with client_for(make_settings, mailer, allowed) as client:
        signup(client, "owner@example.com", "Org")
        for method, path in [
            ("get", f"{APP}/overview"),
            ("get", f"{APP}/projects"),
            ("get", f"{APP}/scans"),
        ]:
            response = getattr(client, method)(path)
            assert response.status_code == 404 and response.json() == NOT_FOUND, (path, response.text)
        created = client.post(f"{APP}/projects", json={"name": "svc"})
        assert created.status_code == 404 and created.json() == NOT_FOUND
        token = make_token(client, "app")
        assert token.status_code == 404 and token.json() == NOT_FOUND


def test_the_answer_is_the_same_as_when_the_feature_is_off(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    off = TestClient(create_app(make_settings(app_scanning_enabled=False), mailer))
    with off as client:
        signup(client, "owner@example.com", "Org")
        off_answer = client.get(f"{APP}/overview")
    with client_for(make_settings, mailer, []) as client:
        client.post(
            f"{API}/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
        )
        on_answer = client.get(f"{APP}/overview")
    assert (on_answer.status_code, on_answer.json()) == (off_answer.status_code, off_answer.json())


def test_only_the_listed_workspace_gets_in(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with client_for(make_settings, mailer, None) as setup:
        signup(setup, "one@example.com", "One")
        one = org_of(setup)
    with client_for(make_settings, mailer, None) as setup:
        setup.post(f"{API}/auth/logout")
        signup(setup, "two@example.com", "Two")
    with client_for(make_settings, mailer, [one]) as client:
        client.post(
            f"{API}/auth/login", json={"email": "two@example.com", "password": "correct-horse-battery-staple"}
        )
        assert client.get(f"{APP}/overview").status_code == 404
    with client_for(make_settings, mailer, [one]) as client:
        client.post(
            f"{API}/auth/login", json={"email": "one@example.com", "password": "correct-horse-battery-staple"}
        )
        assert client.get(f"{APP}/overview").status_code == 200


def test_a_token_made_earlier_stops_when_its_workspace_leaves_the_list(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with client_for(make_settings, mailer, None) as first:
        signup(first, "owner@example.com", "Org")
        pid = new_project(first)
        token = make_token(first, "app").json()["token"]
    headers = {**bearer(token), "Idempotency-Key": "k1", "Content-Type": "application/json"}
    with client_for(make_settings, mailer, []) as client:
        refused = bare(client).post(SUBMIT, content=json.dumps(doc(pid)), headers=headers)
        assert refused.status_code == 404 and refused.json() == NOT_FOUND
        assert bare(client).get(f"{APP}/overview", headers=bearer(token)).status_code in (401, 404)


def test_web_scanning_and_web_tokens_do_not_depend_on_the_list(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with client_for(make_settings, mailer, []) as client:
        signup(client, "owner@example.com", "Org")
        assert client.get(f"{API}/auth/me").status_code == 200
        assert client.get(f"{API}/api-tokens").status_code == 200
        assert make_token(client, "web").status_code == 201


def test_a_production_like_setup_must_name_its_workspaces(make_settings) -> None:  # type: ignore[no-untyped-def]
    production = {
        "public_base_url": "https://example.com",
        "cors_origins": ["https://example.com"],
        "cookie_secure": True,
    }
    with pytest.raises(ValueError, match="ALLOWED_ORGS"):
        make_settings(app_scanning_enabled=True, **production)
    assert make_settings(app_scanning_enabled=True, app_scanning_allowed_orgs=["a"], **production)
    assert make_settings(app_scanning_enabled=True, app_scanning_allowed_orgs=[], **production)
    assert make_settings(app_scanning_enabled=False, **production)


def test_the_list_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURESCOPE_APP_SCANNING_ALLOWED_ORGS", '["abc", "def"]')
    assert Settings().app_scanning_allowed_orgs == ["abc", "def"]
    monkeypatch.delenv("SECURESCOPE_APP_SCANNING_ALLOWED_ORGS")
    assert Settings().app_scanning_allowed_orgs is None
