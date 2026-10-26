"""Re-checking one finding: same safety rules as a scan, nothing stored, never marks a finding resolved."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models.scan import ScanRow
from app.scanner.checks import assess
from app.scanner.fetcher import FetchError
from app.services import recheck as recheck_module
from app.tests.conftest import signup, trust_host
from app.tests.test_finding_lifecycle import API, member_client, run_scan

CSP = "SS-HDR-CSP-001"


def url(scan_id: str, finding: str = CSP) -> str:
    return f"{API}/scans/{scan_id}/findings/{finding}/recheck"


def scans_of(client: TestClient) -> int:
    return len(client.get(f"{API}/scans").json()["items"])


def event_types(client: TestClient) -> list[str]:
    return [e["event_type"] for e in client.get(f"{API}/audit-events?limit=100").json()["items"]]


def test_a_finding_that_is_still_there_says_so_and_stores_nothing(
    local_client: TestClient, mock_server: str
) -> None:
    scan = run_scan(local_client, mock_server)
    before = scans_of(local_client)
    response = local_client.post(url(scan["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "still_present" and body["finding_id"] == CSP
    assert body["host"] == "127.0.0.1" and body["checked_at"]
    assert scans_of(local_client) == before  # no scan was stored or counted
    assert "finding.rechecked" in event_types(local_client)


def test_a_fixed_finding_is_reported_but_not_marked_resolved(
    local_client: TestClient, mock_server: str
) -> None:
    scan = run_scan(local_client, mock_server, "plain")
    # Point the old scan at the hardened page, as if the site had been fixed since.
    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.repo._session.begin() as session:
        session.execute(
            update(ScanRow).where(ScanRow.id == scan["id"]).values(target_url=f"{mock_server}/hardened")
        )
    body = local_client.post(url(scan["id"])).json()
    assert body["outcome"] == "not_seen"
    assert "full scan" in body["message"]
    # The finding keeps its state until a full scan decides.
    after = local_client.get(f"{API}/scans/{scan['id']}").json()
    assert next(f for f in after["findings"] if f["id"] == CSP)["status"] != "resolved"


def test_a_check_that_did_not_run_is_never_reported_as_fixed(
    local_client: TestClient, mock_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan = run_scan(local_client, mock_server)
    real = assess

    def skipped(*args: Any, **kwargs: Any) -> Any:
        assessment = real(*args, **kwargs)
        assessment.findings = []
        monkeypatch.setattr(type(assessment), "unverified_prefixes", property(lambda self: ("SS-HDR",)))
        return assessment

    monkeypatch.setattr("app.services.recheck.assess", skipped)
    body = local_client.post(url(scan["id"])).json()
    assert body["outcome"] == "could_not_check" and "could not run" in body["message"]


def test_an_unreachable_site_is_could_not_check(
    local_client: TestClient, mock_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan = run_scan(local_client, mock_server)

    async def down(*args: Any, **kwargs: Any) -> Any:
        raise FetchError("connection refused")

    monkeypatch.setattr(recheck_module, "collect", down)
    body = local_client.post(url(scan["id"])).json()
    assert body["outcome"] == "could_not_check" and "could not be checked" in body["message"]


def test_it_needs_the_site_to_still_be_verified(local_client: TestClient, mock_server: str) -> None:
    scan = run_scan(local_client, mock_server)
    target = next(
        t for t in local_client.get(f"{API}/targets").json()["items"] if t["hostname"] == "127.0.0.1"
    )
    local_client.delete(f"{API}/targets/{target['id']}").raise_for_status()
    response = local_client.post(url(scan["id"]))
    assert response.status_code == 403 and "not verified" in response.json()["detail"]


def test_unknown_and_malformed_ids_are_not_found(local_client: TestClient, mock_server: str) -> None:
    scan = run_scan(local_client, mock_server)
    assert local_client.post(url(scan["id"], "SS-DOES-NOT-EXIST")).status_code == 404
    assert local_client.post(url(scan["id"], "bad%20id")).status_code == 404
    assert local_client.post(url("0" * 32)).status_code == 404


def test_other_workspaces_and_viewers_and_anonymous_are_refused(
    local_client: TestClient, mock_server: str
) -> None:
    scan = run_scan(local_client, mock_server)
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    bob = TestClient(local_client.app)
    signup(bob, "bob@example.com", "Bob Org")
    assert bob.post(url(scan["id"])).status_code == 404  # another customer's scan does not exist for Bob
    viewer = member_client(local_client, org, "viewer@example.com", "VIEWER")
    assert viewer.post(url(scan["id"])).status_code == 403
    assert TestClient(local_client.app).post(url(scan["id"])).status_code in (401, 403)


def test_rechecks_are_rate_limited_per_site(make_settings, mailer, mock_server: str) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(
        allow_private_targets=True, request_timeout_seconds=1.0, rechecks_per_target_per_hour=2
    )
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        scan = run_scan(client, mock_server)
        codes = [client.post(url(scan["id"])).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
