"""Idempotency keys on scan creation: a repeated request returns the scan already made."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.scans import IdempotencyKeyTaken
from app.tests.conftest import signup, trust_host
from app.tests.test_db_and_reports import make_org, make_repo
from app.tests.test_finding_lifecycle import API
from app.tests.test_scan_control import event_types, wait_for

KEY = "0f6c1c9e-3a5b-4f7e-9d2a-7b1c2d3e4f50"


def make_client(make_settings: Any, mailer: Any, **limits: Any) -> Iterator[TestClient]:
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0, **limits)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        yield client


@pytest.fixture
def roomy_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    """Rate limits high enough that only the idempotency behaviour decides what happens."""
    yield from make_client(make_settings, mailer, scans_per_target_per_hour=50, scans_per_client_per_hour=50)


@pytest.fixture
def tight_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    yield from make_client(make_settings, mailer, scans_per_target_per_hour=1, scans_per_client_per_hour=50)


def post(client: TestClient, mock_server: str, path: str = "plain", key: str | None = KEY):  # type: ignore[no-untyped-def]
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(
        f"{API}/scans",
        json={"url": f"{mock_server}/{path}", "authorization_confirmed": True},
        headers=headers,
    )


def scan_count(client: TestClient) -> int:
    return int(client.get(f"{API}/scans").json()["total"])


def test_the_same_key_twice_makes_one_scan(local_client: TestClient, mock_server: str) -> None:
    first = post(local_client, mock_server)
    second = post(local_client, mock_server)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert "idempotent-replayed" not in first.headers
    assert second.headers["Idempotent-Replayed"] == "true"
    assert scan_count(local_client) == 1
    assert event_types(local_client).count("scan.created") == 1


def test_a_replay_after_the_scan_finished_still_returns_that_scan(
    local_client: TestClient, mock_server: str
) -> None:
    scan_id = post(local_client, mock_server).json()["id"]
    wait_for(local_client, scan_id, "completed", "failed")
    again = post(local_client, mock_server)
    assert again.json()["id"] == scan_id and scan_count(local_client) == 1


def test_a_replay_does_not_use_a_rate_limit_slot(tight_client: TestClient, mock_server: str) -> None:
    assert post(tight_client, mock_server).status_code == 202  # the one allowed scan of this site this hour
    for _ in range(3):  # would be 429 if each replay counted as a new scan of this site
        assert post(tight_client, mock_server).status_code == 202
    assert post(tight_client, mock_server, key="another-key-0001").status_code == 429


def test_requests_without_a_key_or_with_different_keys_make_separate_scans(
    roomy_client: TestClient, mock_server: str
) -> None:
    local_client = roomy_client
    a = post(local_client, mock_server, key=None).json()["id"]
    b = post(local_client, mock_server, key=None).json()["id"]
    c = post(local_client, mock_server, key="key-number-0001").json()["id"]
    d = post(local_client, mock_server, key="key-number-0002").json()["id"]
    assert len({a, b, c, d}) == 4 and scan_count(local_client) == 4


def test_the_same_key_for_another_site_is_refused_and_makes_nothing(
    local_client: TestClient, mock_server: str
) -> None:
    trust_host(local_client, "localhost")
    first = post(local_client, mock_server)
    other_site = local_client.post(
        f"{API}/scans",
        json={
            "url": mock_server.replace("127.0.0.1", "localhost") + "/plain",
            "authorization_confirmed": True,
        },
        headers={"Idempotency-Key": KEY},
    )
    assert first.status_code == 202
    assert other_site.status_code == 422, other_site.text
    assert scan_count(local_client) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "short",
        "a" * 81,
        "has space in it",
        "semi;colon-key-1",
        "quote'key-12345",
        "new\tline-key-1",
        "ünïcode-key-12",
    ],
)
def test_keys_of_the_wrong_shape_are_rejected(local_client: TestClient, mock_server: str, bad: str) -> None:
    try:
        response = post(local_client, mock_server, key=bad)
    except UnicodeEncodeError:  # the HTTP client itself refuses non-ASCII header values
        return
    assert response.status_code == 400, response.text
    assert scan_count(local_client) == 0


def test_a_key_is_private_to_its_workspace(roomy_client: TestClient, mock_server: str) -> None:
    local_client = roomy_client
    mine = post(local_client, mock_server).json()["id"]
    bob = TestClient(local_client.app)
    signup(bob, "bob@example.com", "Bob Org")
    trust_host(bob, "127.0.0.1")
    theirs = post(bob, mock_server)
    assert theirs.status_code == 202
    assert theirs.json()["id"] != mine  # bob's request did not get alice's scan
    assert "idempotent-replayed" not in theirs.headers
    assert bob.get(f"{API}/scans/{mine}").status_code == 404
    assert scan_count(bob) == 1 and scan_count(local_client) == 1


def test_the_database_allows_a_key_only_once_per_workspace(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = repo.create_scan(org, user, "https://a.example/", "a.example", idempotency_key=KEY)
    with pytest.raises(IdempotencyKeyTaken):  # what a lost race between two identical requests looks like
        repo.create_scan(org, user, "https://a.example/", "a.example", idempotency_key=KEY)
    assert repo.find_by_idempotency_key(org, KEY) == (first, "a.example")
    assert repo.find_by_idempotency_key(org, "no-such-key-0001") is None
    repo.create_scan(org, user, "https://a.example/", "a.example")  # no key: any number of scans
    repo.create_scan(org, user, "https://a.example/", "a.example")
