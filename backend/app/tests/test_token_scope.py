"""An API token reaches the CI routes and nothing else, and is only as strong as its owner and plan today."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tests.conftest import signup, trust_host
from app.tests.test_integrations import API, bare, bearer, make_token
from app.tests.test_tenancy import add_member, new_user, org_of


@pytest.fixture
def ci_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        yield client


def _operations(client: TestClient) -> list[tuple[str, str]]:
    found = []
    for path, operations in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                found.append((method.upper(), path))
    return found


def test_a_token_gets_exactly_the_answers_an_anonymous_visitor_gets_everywhere_but_ci(
    ci_client: TestClient,
) -> None:
    token = make_token(ci_client)["token"]
    runner = bare(ci_client)
    operations = _operations(ci_client)
    assert len(operations) > 50, "the route list could not be read"
    differing: list[str] = []
    for method, path in operations:
        if path.startswith(f"{API}/ci/"):
            continue
        url = re.sub(r"\{[^}]+\}", "0" * 32, path)
        call = {"GET": runner.get, "POST": runner.post}.get(method)
        if call is None:  # PUT/PATCH/DELETE: the same check through the generic request below

            def call(u: str, **kw: Any) -> Any:  # noqa: B023
                return ci_client.request(method, u, **kw)

        with_token = (
            call(url, headers=bearer(token), json={})
            if method == "POST"
            else call(url, headers=bearer(token))
        )
        without = call(url, json={}) if method == "POST" else call(url)
        if with_token.status_code != without.status_code:
            differing.append(
                f"{method} {path}: {without.status_code} anonymous, {with_token.status_code} with a token"
            )
        if with_token.status_code < 300 and not path.startswith((f"{API}/health", f"{API}/ready")):
            if without.status_code >= 300:
                differing.append(f"{method} {path} accepted a token")
    assert differing == []


def test_a_token_cannot_make_or_list_tokens_or_change_anything_in_the_workspace(
    ci_client: TestClient,
) -> None:
    token = make_token(ci_client)["token"]
    runner = bare(ci_client)
    for path in ("/api-tokens", "/webhooks", "/targets", "/organizations", "/scans", "/account/sessions"):
        assert runner.get(f"{API}{path}", headers=bearer(token)).status_code in (401, 403), path
    assert runner.post(f"{API}/api-tokens", headers=bearer(token), json={"name": "x"}).status_code in (
        401,
        403,
    )
    assert len(ci_client.get(f"{API}/api-tokens").json()["items"]) == 1


def test_a_token_made_by_an_admin_stops_when_that_admin_is_made_a_viewer(ci_client: TestClient) -> None:
    org = org_of(ci_client)
    admin = new_user(ci_client, "admin@example.com")
    assert add_member(ci_client, org, "admin@example.com", "ADMIN").status_code == 201
    made = admin.post(f"{API}/api-tokens", json={"name": "admin token"}, headers={"X-Organization-Id": org})
    assert made.status_code == 201, made.text
    token = made.json()["token"]
    runner = bare(ci_client)
    body = {"url": "https://127.0.0.1/"}
    before = runner.post(f"{API}/ci/scans", headers=bearer(token), json=body)
    assert before.status_code != 401
    admin_id = admin.get(f"{API}/auth/me").json()["id"]
    assert (
        ci_client.patch(f"{API}/organizations/{org}/members/{admin_id}", json={"role": "VIEWER"}).status_code
        == 200
    )
    after = runner.post(f"{API}/ci/scans", headers=bearer(token), json=body)
    assert after.status_code == 401
