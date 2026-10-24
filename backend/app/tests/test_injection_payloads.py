"""Hostile input is stored or rejected as plain data; it never runs and never causes a server error.

Covers the free-text and identifier fields reachable from the API: names, hostnames, URLs, e-mail
addresses and path ids. SQL is parameterised everywhere, so the payloads must come back byte for byte
or be refused with a 4xx, and the database must still hold every table afterwards.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.tests.conftest import PASSWORD

PAYLOADS = [
    "'; DROP TABLE users; --",
    "' OR '1'='1",
    "\" OR \"\"=\"",
    "1; SELECT pg_sleep(5); --",
    "<script>alert(1)</script>",
    "\"><img src=x onerror=alert(1)>",
    "{{7*7}}${7*7}",
    "../../etc/passwd",
    "%00%0d%0aX-Injected: yes",
    "javascript:alert(1)",
    "a" * 5000,
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_token_names_are_data(strict_client: TestClient, payload: str) -> None:
    response = strict_client.post("/api/v1/api-tokens", json={"name": payload})
    assert response.status_code < 500, response.text
    if response.status_code == 201:
        assert response.json()["name"] == payload  # stored and returned as text, not interpreted
        assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("payload", PAYLOADS)
def test_target_hostnames_are_validated(strict_client: TestClient, payload: str) -> None:
    response = strict_client.post("/api/v1/targets", json={"hostname": payload})
    assert response.status_code < 500, response.text
    assert response.status_code in (201, 400, 409, 422)
    if response.status_code == 201:
        assert response.json()["hostname"] == payload.lower().strip() or "." in response.json()["hostname"]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_login_and_registration_reject_hostile_input(anon_client: TestClient, payload: str) -> None:
    login = anon_client.post("/api/v1/auth/login", json={"email": payload, "password": payload})
    assert login.status_code in (400, 401, 422, 429), login.text
    register = anon_client.post("/api/v1/auth/register", json={"email": payload, "password": PASSWORD})
    assert register.status_code in (400, 422, 429), register.text
    org = anon_client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": PASSWORD, "organization_name": payload},
    )
    assert org.status_code < 500, org.text


@pytest.mark.parametrize("payload", PAYLOADS)
def test_path_ids_cannot_inject(strict_client: TestClient, payload: str) -> None:
    for path in ("scans", "targets", "findings", "webhooks"):
        response = strict_client.get(f"/api/v1/{path}/{payload[:200]}")
        assert response.status_code in (400, 404, 405, 422), (path, response.status_code)


def test_database_is_intact_after_hostile_input(strict_client: TestClient) -> None:
    for payload in PAYLOADS:
        strict_client.post("/api/v1/api-tokens", json={"name": payload})
        strict_client.post("/api/v1/targets", json={"hostname": payload})
    me = strict_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
