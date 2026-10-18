"""Cancelling and retrying scans."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.schemas.scan import Finding, ScanStatus, Severity, TargetMetadata
from app.tests.conftest import signup, trust_host
from app.tests.test_db_and_reports import make_org, make_repo
from app.tests.test_finding_lifecycle import API, member_client, run_scan
from app.tests.test_overview import complete

META = TargetMetadata(requested_url="https://a.example/", host="a.example")


def start(client: TestClient, mock_server: str, path: str) -> str:
    response = client.post(
        f"{API}/scans", json={"url": f"{mock_server}/{path}", "authorization_confirmed": True}
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


def wait_for(client: TestClient, scan_id: str, *statuses: str, seconds: float = 10) -> dict:  # type: ignore[type-arg]
    deadline = time.time() + seconds
    while time.time() < deadline:
        detail = client.get(f"{API}/scans/{scan_id}").json()
        if detail["status"] in statuses:
            return detail  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError(f"scan never reached {statuses}")


def event_types(client: TestClient) -> list[str]:
    return [e["event_type"] for e in client.get(f"{API}/audit-events?limit=100").json()["items"]]


# --- repository level: the database decides every race ---------------------------------------------


def test_a_scan_cancelled_before_it_finishes_keeps_its_cancelled_state(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    scan_id = repo.create_scan(org, user, "https://a.example/", "a.example")
    assert repo.mark_running(scan_id) is True
    assert repo.cancel_scan(scan_id, org) is True
    # The scanner finishes a moment later: its result is thrown away.
    finding = Finding(id="SS-1", title="t", severity=Severity.HIGH, category="c", description="d", remediation="r")
    assert repo.complete_scan(scan_id, [finding], 50, "C", META) is False
    repo.fail_scan(scan_id, "late failure")
    detail = repo.get_scan(scan_id, org)
    assert detail is not None
    assert detail.status is ScanStatus.CANCELLED
    assert detail.findings == [] and detail.score is None and detail.finished_at is not None
    assert detail.error == "Cancelled before it finished."


def test_a_scan_cancelled_while_queued_never_starts(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    scan_id = repo.create_scan(org, user, "https://a.example/", "a.example")
    assert repo.cancel_scan(scan_id, org) is True
    assert repo.mark_running(scan_id) is False


def test_finished_scans_and_other_organizations_cannot_be_cancelled(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    other_org, _ = make_org(db_url, "other@example.com")
    done = complete(repo, org, user, 90, [])
    assert repo.cancel_scan(done, org) is False
    waiting = repo.create_scan(org, user, "https://a.example/", "a.example")
    assert repo.cancel_scan(waiting, other_org) is False  # not their scan
    assert repo.cancel_scan(waiting, org) is True


def test_cancelled_scans_do_not_touch_the_overview_or_finding_states(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    finding = Finding(id="SS-1", title="t", severity=Severity.HIGH, category="c", description="d", remediation="r")
    complete(repo, org, user, 70, [finding])
    later = repo.create_scan(org, user, "https://a.example/", "a.example")
    repo.cancel_scan(later, org)
    (site,) = repo.overview(org).sites
    assert site.score == 70 and site.open_total == 1 and len(site.history) == 1  # still open, not resolved


# --- API --------------------------------------------------------------------------------------------


def test_cancelling_a_running_scan_stops_it_and_is_audited(local_client: TestClient, mock_server: str) -> None:
    local_client.app.state.s.settings.request_timeout_seconds = 8  # type: ignore[attr-defined]
    scan_id = start(local_client, mock_server, "slow")  # the mock takes 3 seconds to answer
    wait_for(local_client, scan_id, "running")
    response = local_client.post(f"{API}/scans/{scan_id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    tasks = local_client.app.state.s.scan_tasks  # type: ignore[attr-defined]
    deadline = time.time() + 3
    while tasks and time.time() < deadline:
        time.sleep(0.05)
    assert scan_id not in tasks  # the scanner task really stopped
    assert local_client.get(f"{API}/scans/{scan_id}").json()["status"] == "cancelled"
    assert "scan.cancelled" in event_types(local_client)
    again = local_client.post(f"{API}/scans/{scan_id}/cancel")
    assert again.status_code == 409


def test_a_finished_scan_cannot_be_cancelled(local_client: TestClient, mock_server: str) -> None:
    detail = run_scan(local_client, mock_server)
    response = local_client.post(f"{API}/scans/{detail['id']}/cancel")
    assert response.status_code == 409
    assert local_client.get(f"{API}/scans/{detail['id']}").json()["status"] == "completed"


def test_retry_runs_a_new_scan_of_the_same_address(local_client: TestClient, mock_server: str) -> None:
    scan_id = start(local_client, mock_server, "slow")  # request timeout is 1s, so this fails
    original = wait_for(local_client, scan_id, "failed")
    retried = local_client.post(f"{API}/scans/{scan_id}/retry")
    assert retried.status_code == 202, retried.text
    new = retried.json()
    assert new["id"] != scan_id and new["target_url"] == original["target_url"]
    assert new["status"] in ("queued", "running", "failed")
    assert local_client.get(f"{API}/scans/{scan_id}").json()["status"] == "failed"  # history is kept
    types = event_types(local_client)
    assert "scan.retried" in types and types.count("scan.created") == 2


def test_only_failed_or_cancelled_scans_can_be_retried(local_client: TestClient, mock_server: str) -> None:
    done = run_scan(local_client, mock_server)
    assert local_client.post(f"{API}/scans/{done['id']}/retry").status_code == 409
    local_client.app.state.s.settings.request_timeout_seconds = 8  # type: ignore[attr-defined]
    running = start(local_client, mock_server, "slow")
    assert local_client.post(f"{API}/scans/{running}/retry").status_code == 409
    assert local_client.post(f"{API}/scans/{running}/cancel").status_code == 200
    assert local_client.post(f"{API}/scans/{running}/retry").status_code == 202


def test_retry_checks_ownership_again(local_client: TestClient, mock_server: str) -> None:
    scan_id = start(local_client, mock_server, "slow")
    wait_for(local_client, scan_id, "failed")
    targets = local_client.get(f"{API}/targets").json()["items"]
    for target in targets:
        assert local_client.delete(f"{API}/targets/{target['id']}").status_code == 204
    response = local_client.post(f"{API}/scans/{scan_id}/retry")
    assert response.status_code == 403 and "verified" in response.json()["detail"]
    trust_host(local_client, "127.0.0.1")
    assert local_client.post(f"{API}/scans/{scan_id}/retry").status_code == 202


def test_other_organizations_and_unknown_scans_are_not_found(
    local_client: TestClient, mock_server: str
) -> None:
    bob_client = TestClient(local_client.app)
    signup(bob_client, "bob@example.com", "Bob Org")
    scan_id = start(local_client, mock_server, "slow")
    wait_for(local_client, scan_id, "failed")
    for action in ("cancel", "retry"):
        assert bob_client.post(f"{API}/scans/{scan_id}/{action}").status_code == 404
        assert local_client.post(f"{API}/scans/{'0' * 32}/{action}").status_code == 404
        assert local_client.post(f"{API}/scans/not-a-valid-id!/{action}").status_code == 404


def test_viewers_cannot_cancel_or_retry_but_members_can(local_client: TestClient, mock_server: str) -> None:
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    scan_id = start(local_client, mock_server, "slow")
    wait_for(local_client, scan_id, "failed")
    viewer = member_client(local_client, org, "viewer@example.com", "VIEWER")
    for action in ("cancel", "retry"):
        assert viewer.post(f"{API}/scans/{scan_id}/{action}").status_code == 403
    member = member_client(local_client, org, "member@example.com", "MEMBER")
    assert member.post(f"{API}/scans/{scan_id}/retry").status_code == 202


def test_requires_sign_in_and_csrf(local_client: TestClient, mock_server: str) -> None:
    anon_client = TestClient(local_client.app)
    assert anon_client.post(f"{API}/scans/{'0' * 32}/cancel").status_code == 401
    scan_id = start(local_client, mock_server, "slow")
    wait_for(local_client, scan_id, "failed")
    headers = dict(local_client.headers)
    local_client.headers.pop("X-CSRF-Token")
    try:
        assert local_client.post(f"{API}/scans/{scan_id}/retry").status_code == 403
    finally:
        local_client.headers.update(headers)
