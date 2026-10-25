"""The overview: per-site posture from completed scans only, scoped to one organization."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from app.repositories.scans import ScanRepository
from app.scanner.fingerprint import fingerprint
from app.schemas.scan import Confidence, Finding, FindingStatus, Severity, TargetMetadata
from app.tests.test_db_and_reports import make_org, make_repo
from app.tests.test_finding_lifecycle import API, member_client, run_scan

HOST = "a.example"


def finding(
    finding_id: str, severity: Severity = Severity.LOW, confidence: Confidence = Confidence.HIGH
) -> Finding:
    return Finding(
        id=finding_id,
        title=f"Title {finding_id}",
        severity=severity,
        category="c",
        description="d",
        remediation="r",
        confidence=confidence,
    )


def complete(
    repo: ScanRepository, org: str, user: str, score: int, findings: list[Finding], host: str = HOST
) -> str:
    time.sleep(0.01)  # scans are ordered by creation time; keep it strictly increasing
    scan_id = repo.create_scan(org, user, f"https://{host}/", host)
    meta = TargetMetadata(requested_url=f"https://{host}/", host=host)
    repo.complete_scan(scan_id, findings, score, "A", meta)
    return scan_id


def test_empty_organization_has_an_empty_overview(db_url: str) -> None:
    repo, (org, _user) = make_repo(db_url), make_org(db_url)
    result = repo.overview(org)
    assert result.sites == [] and result.fix_first is None and result.other_open == 0


def test_site_posture_has_change_history_and_open_counts(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = complete(repo, org, user, 76, [finding("SS-1", Severity.HIGH), finding("SS-2")])
    complete(repo, org, user, 84, [finding("SS-1", Severity.HIGH), finding("SS-2")])
    latest = complete(repo, org, user, 90, [finding("SS-1", Severity.HIGH)])

    (site,) = repo.overview(org).sites
    assert site.host == HOST and site.latest_scan_id == latest
    assert (site.score, site.previous_score, site.score_change) == (90, 84, 6)
    assert [p.score for p in site.history] == [76, 84, 90]  # oldest first
    assert site.history[0].scan_id == first
    assert site.open_counts == {"high": 1} and site.open_total == 1
    assert site.top_finding is not None and site.top_finding.finding_id == "SS-1"
    # SS-2 was not reported by the latest scan, so its state became resolved and it is not counted.


def test_only_open_findings_count_and_the_most_severe_comes_first(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    scan_id = complete(
        repo,
        org,
        user,
        70,
        [
            finding("HIGH-ACCEPTED", Severity.HIGH),
            finding("MED-HEURISTIC", Severity.MEDIUM, Confidence.MEDIUM),
            finding("MED-SURE", Severity.MEDIUM),
            finding("LOW-1", Severity.LOW),
        ],
    )
    repo.set_finding_status(org, fingerprint(HOST, "HIGH-ACCEPTED"), FindingStatus.ACCEPTED_RISK, None, user)
    result = repo.overview(org)
    (site,) = result.sites
    assert site.latest_scan_id == scan_id
    assert site.open_counts == {"medium": 2, "low": 1} and site.open_total == 3
    assert (
        result.fix_first is not None and result.fix_first.finding_id == "MED-SURE"
    )  # certain beats heuristic
    assert result.other_open == 2


def test_failed_scans_and_other_hosts_are_handled(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    complete(repo, org, user, 100, [], host="a.example")
    failed = repo.create_scan(org, user, "https://a.example/", "a.example")
    repo.fail_scan(failed, "boom")
    complete(repo, org, user, 60, [finding("SS-9", Severity.CRITICAL)], host="b.example")

    result = repo.overview(org)
    by_host = {s.host: s for s in result.sites}
    assert set(by_host) == {"a.example", "b.example"}
    assert (
        by_host["a.example"].score_change is None and len(by_host["a.example"].history) == 1
    )  # failed ignored
    assert result.sites[0].host == "b.example"  # most recently scanned first
    assert result.fix_first is not None and result.fix_first.host == "b.example"


def test_history_is_capped_and_sites_are_capped(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    for score in range(1, 16):
        complete(repo, org, user, score, [])
    (site,) = repo.overview(org, history=12).sites
    assert [p.score for p in site.history] == list(range(4, 16))
    for index in range(3):
        complete(repo, org, user, 50, [], host=f"h{index}.example")
    assert len(repo.overview(org, max_sites=2).sites) == 2


def test_more_than_six_sites_still_reports_every_scanned_host(db_url: str) -> None:
    repo = make_repo(db_url)
    org, user = make_org(db_url)
    other_org, other_user = make_org(db_url, "other@example.com")
    hosts = [f"h{index}.example" for index in range(9)]
    for host in hosts:
        complete(repo, org, user, 70, [], host=host)
    never = repo.create_scan(org, user, "https://failed-only.example/", "failed-only.example")
    repo.fail_scan(never, "boom")
    complete(repo, other_org, other_user, 50, [], host="other-org.example")

    result = repo.overview(org)
    assert len(result.sites) == 6  # the listed sites stay capped
    assert result.scanned_hosts == sorted(hosts)  # but every completed host is reported
    assert "failed-only.example" not in result.scanned_hosts  # a failed scan is not a completed one
    assert "other-org.example" not in result.scanned_hosts


def test_scanned_hosts_are_not_limited_by_the_recent_scan_window(db_url: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.repositories.scans.OVERVIEW_SCAN_WINDOW", 2)
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    complete(repo, org, user, 80, [], host="old.example")
    for _ in range(3):
        complete(repo, org, user, 60, [], host="busy.example")
    result = repo.overview(org)
    assert [s.host for s in result.sites] == ["busy.example"]  # old.example fell out of the window
    assert result.scanned_hosts == ["busy.example", "old.example"]


def test_other_organizations_never_appear(db_url: str) -> None:
    repo = make_repo(db_url)
    org_a, user_a = make_org(db_url, "a@example.com")
    org_b, user_b = make_org(db_url, "b@example.com")
    complete(repo, org_a, user_a, 90, [finding("SS-1", Severity.HIGH)])
    complete(repo, org_b, user_b, 10, [finding("SS-2", Severity.CRITICAL)], host="secret.example")
    a, b = repo.overview(org_a), repo.overview(org_b)
    assert (
        [s.host for s in a.sites] == [HOST] and a.fix_first is not None and a.fix_first.finding_id == "SS-1"
    )
    assert [s.host for s in b.sites] == ["secret.example"]


def test_api_requires_sign_in_and_is_open_to_every_role(
    local_client: TestClient, mock_server: str, anon_client: TestClient
) -> None:
    assert anon_client.get(f"{API}/overview").status_code == 401
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    assert local_client.get(f"{API}/overview").json() == {
        "sites": [],
        "fix_first": None,
        "other_open": 0,
        "scanned_hosts": [],
    }

    run_scan(local_client, mock_server)
    body = local_client.get(f"{API}/overview").json()
    assert len(body["sites"]) == 1 and body["sites"][0]["history"][0]["score"] == body["sites"][0]["score"]
    assert body["scanned_hosts"] == [body["sites"][0]["host"]]
    assert body["fix_first"]["scan_id"] == body["sites"][0]["latest_scan_id"]

    viewer = member_client(local_client, org, "viewer@example.com", "VIEWER")
    assert viewer.get(f"{API}/overview").json() == body


def test_the_scan_list_costs_the_same_number_of_queries_for_a_big_page_as_for_a_small_one(
    make_settings: Any,
    mailer: Any,
    mock_server: str,
) -> None:
    """A page of scans is loaded with a fixed number of queries; it must not grow with the number of scans."""
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from app.main import create_app
    from app.tests.conftest import signup, trust_host
    from app.tests.test_tenancy import finished_scan

    settings = make_settings(
        allow_private_targets=True,
        request_timeout_seconds=1.0,
        scans_per_target_per_hour=100,
        scans_per_client_per_hour=100,
    )
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        for _ in range(7):
            finished_scan(client, mock_server)
        counted: list[int] = []
        event.listen(
            client.app.state.s.engine,  # type: ignore[attr-defined]
            "before_cursor_execute",
            lambda *a, **k: counted.append(1),
        )
        client.get("/api/v1/scans?limit=1")
        small = len(counted)
        counted.clear()
        client.get("/api/v1/scans?limit=25")
        assert len(counted) == small
