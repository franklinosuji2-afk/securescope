"""Scheduled scans, alert rules and the cron endpoint."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models.schedule import ScanScheduleRow
from app.schemas.scan import Finding, ScanDetail, ScanStatus, Severity
from app.services.alerts import build_body, decide
from app.tests.conftest import CapturingMailer, signup, trust_host
from app.tests.test_tenancy import add_member, new_user, org_of

SECRET = "s" * 40
CRON = "/api/v1/internal/run-due"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def target_id_of(client: TestClient, host: str = "127.0.0.1") -> str:
    items = client.get("/api/v1/targets").json()["items"]
    return str(next(t["id"] for t in items if t["hostname"] == host))


@pytest.fixture
def cron_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0, cron_secret=SECRET)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        yield client


def run_cron(client: TestClient, secret: str | None = SECRET) -> dict[str, int]:
    headers = {"X-Cron-Secret": secret} if secret is not None else {}
    response = client.post(CRON, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def make_due(client: TestClient) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.schedules._session.begin() as session:
        session.execute(update(ScanScheduleRow).values(next_run_at=datetime.now(UTC) - timedelta(minutes=1)))


# --- alert rules (pure) -------------------------------------------------------------------------------


def finding(fid: str, severity: Severity) -> Finding:
    return Finding(
        id=fid,
        title=f"Title {fid}",
        severity=severity,
        category="headers",
        description="d",
        remediation="r",
        fingerprint=f"fp-{fid}",
    )


def scan(findings: list[Finding], score: int, minutes: int = 0, status: ScanStatus = ScanStatus.COMPLETED) -> ScanDetail:
    return ScanDetail(
        id=f"scan{minutes}",
        target_url="https://a.example",
        host="a.example",
        status=status,
        score=score,
        grade="B",
        created_at=T0 + timedelta(minutes=minutes),
        findings=findings,
    )


def test_no_alert_when_nothing_changed() -> None:
    a = scan([finding("A", Severity.LOW)], 90, 0)
    b = scan([finding("A", Severity.LOW)], 90, 10)
    assert decide(a, b).send is False


def test_no_alert_for_the_first_scan_of_a_site() -> None:
    assert decide(None, scan([finding("A", Severity.HIGH)], 60)).send is False


def test_a_new_finding_triggers_an_alert_that_names_it() -> None:
    a = scan([], 100, 0)
    b = scan([finding("N", Severity.MEDIUM)], 90, 10)
    decision = decide(a, b)
    assert decision.send is True
    assert "1 new finding" in decision.subject
    body = build_body(decision, b, "https://app.example")
    assert "Title N" in body
    assert "https://app.example/#/findings?scan=scan10" in body


def test_new_informational_notes_alone_do_not_alert() -> None:
    a = scan([], 100, 0)
    b = scan([finding("I", Severity.INFO)], 100, 10)
    assert decide(a, b).send is False


def test_a_resolved_finding_never_alerts() -> None:
    a = scan([finding("A", Severity.HIGH)], 80, 0)
    b = scan([], 100, 10)
    assert decide(a, b).send is False


def test_a_big_score_drop_alerts_even_without_new_findings() -> None:
    a = scan([finding("A", Severity.LOW)], 95, 0)
    b = scan([finding("A", Severity.LOW)], 85, 10)
    assert decide(a, b).send is True
    assert decide(scan([], 95, 0), scan([], 92, 10)).send is False


def test_a_certificate_that_is_about_to_expire_alerts_by_email_and_webhook() -> None:
    """The "expires soon" finding (SS-TLS-CERT-001, scanner/checks.py) is a new finding in the first scan after
    the certificate gets close to its end, so the ordinary alert rule covers it; there is no separate alert."""
    healthy = scan([], 100, 0)
    expiring = scan([finding("SS-TLS-CERT-001", Severity.MEDIUM)], 90, 10)
    decision = decide(healthy, expiring)
    assert decision.send is True
    assert [f.id for f in decision.new_findings] == ["SS-TLS-CERT-001"]
    # The next scheduled run, with the same finding still open, stays quiet instead of repeating the alert.
    assert decide(expiring, scan([finding("SS-TLS-CERT-001", Severity.HIGH)], 90, 20)).send is False


def test_a_failed_scheduled_scan_alerts() -> None:
    failed = scan([], 0, 10, ScanStatus.FAILED)
    assert decide(None, failed).send is True


# --- plan gating and permissions -----------------------------------------------------------------------


@pytest.fixture
def free_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(default_plan=None, allow_private_targets=True), mailer)) as client:
        signup(client, "free@example.com", "Free Org")
        trust_host(client, "127.0.0.1")
        yield client


def test_a_free_workspace_cannot_schedule_but_can_see_why(free_client: TestClient) -> None:
    listing = free_client.get("/api/v1/schedules").json()
    assert listing["available"] is False
    tid = target_id_of(free_client)
    response = free_client.put(f"/api/v1/schedules/{tid}", json={"frequency": "daily", "notify": True})
    assert response.status_code == 403
    assert "Professional and Agency" in response.json()["detail"]


def test_the_plan_summary_says_whether_scheduling_is_included(
    free_client: TestClient, local_client: TestClient
) -> None:
    free = free_client.get(f"/api/v1/organizations/{org_of(free_client)}/plan").json()
    internal = local_client.get(f"/api/v1/organizations/{org_of(local_client)}/plan").json()
    assert free["limits"]["scheduled_scans"] is False
    assert internal["limits"]["scheduled_scans"] is True


def test_only_people_who_manage_sites_can_change_a_schedule(local_client: TestClient, make_settings) -> None:  # type: ignore[no-untyped-def]
    tid = target_id_of(local_client)
    org = org_of(local_client)
    for role, allowed in (("MEMBER", False), ("VIEWER", False), ("SECURITY_ANALYST", True), ("ADMIN", True)):
        email = f"{role.lower()}@example.com"
        other = new_user(local_client, email)
        add_member(local_client, org, email, role)
        response = other.put(
            f"/api/v1/schedules/{tid}",
            json={"frequency": "weekly", "notify": False},
            headers={"X-Organization-Id": org},
        )
        assert (response.status_code == 200) is allowed, (role, response.text)


def test_the_address_must_be_on_the_verified_site(local_client: TestClient) -> None:
    tid = target_id_of(local_client)
    bad = local_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": True, "url": "https://evil.example/"},
    )
    assert bad.status_code == 400
    assert local_client.get("/api/v1/schedules").json()["items"][0]["frequency"] == "off"


def test_a_site_of_another_workspace_cannot_be_scheduled(local_client: TestClient) -> None:
    tid = target_id_of(local_client)
    other = TestClient(local_client.app)
    signup(other, "bob@example.com", "Bob Org")
    response = other.put(f"/api/v1/schedules/{tid}", json={"frequency": "daily", "notify": True})
    assert response.status_code == 404
    assert other.get("/api/v1/schedules").json()["items"] == []


def test_schedules_need_a_signed_in_user(anon_client: TestClient) -> None:
    assert anon_client.get("/api/v1/schedules").status_code == 401
    assert anon_client.put("/api/v1/schedules/abc", json={"frequency": "daily"}).status_code == 401


# --- the cron endpoint ---------------------------------------------------------------------------------


def test_the_endpoint_does_not_exist_without_a_secret(local_client: TestClient) -> None:
    assert local_client.post(CRON, headers={"X-Cron-Secret": SECRET}).status_code == 404


def test_a_wrong_or_missing_secret_is_refused(cron_client: TestClient) -> None:
    assert cron_client.post(CRON).status_code == 401
    assert cron_client.post(CRON, headers={"X-Cron-Secret": "x" * 40}).status_code == 401


def test_a_short_secret_is_rejected_at_start_up(make_settings) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        make_settings(cron_secret="short")


def test_a_due_schedule_runs_once_and_is_then_not_due(cron_client: TestClient, mock_server: str) -> None:
    tid = target_id_of(cron_client)
    cron_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"},
    ).raise_for_status()
    first = run_cron(cron_client)
    assert first == {"due": 1, "scans_started": 1, "alerts_sent": 0, "skipped": 0}
    again = run_cron(cron_client)
    assert again["due"] == 0
    item = cron_client.get("/api/v1/schedules").json()["items"][0]
    assert item["last_scan_id"] is not None
    assert item["last_outcome"].startswith("completed")
    assert datetime.fromisoformat(item["next_run_at"]) > datetime.now(UTC) + timedelta(hours=23)
    assert cron_client.get(f"/api/v1/scans/{item['last_scan_id']}").json()["status"] == "completed"


def test_overlapping_calls_never_run_the_same_schedule_twice(cron_client: TestClient, mock_server: str) -> None:
    tid = target_id_of(cron_client)
    cron_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": False, "url": f"{mock_server}/hardened"},
    ).raise_for_status()
    state = cron_client.app.state.s  # type: ignore[attr-defined]
    results: list[int] = []

    def claim() -> None:
        results.append(len(state.schedules.claim_due(datetime.now(UTC), 5)))

    threads = [threading.Thread(target=claim) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(results) == 1


def test_a_worse_second_run_emails_workspace_members_only(
    cron_client: TestClient, mock_server: str, mailer: CapturingMailer
) -> None:
    org = org_of(cron_client)
    viewer = new_user(cron_client, "viewer@example.com")
    add_member(cron_client, org, "viewer@example.com", "VIEWER")
    mailer.sent.clear()
    tid = target_id_of(cron_client)
    cron_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"},
    ).raise_for_status()
    run_cron(cron_client)
    assert mailer.sent == []  # the first scan of a site never alerts
    cron_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": True, "url": f"{mock_server}/plain"},
    ).raise_for_status()
    make_due(cron_client)
    summary = run_cron(cron_client)
    assert summary["scans_started"] == 1
    assert summary["alerts_sent"] >= 1
    recipients = {to for to, _, _ in mailer.sent}
    assert recipients == {"alice@example.com"}  # the viewer gets nothing
    assert "new finding" in mailer.sent[-1][1]
    assert "SECRETVALUE123" not in mailer.sent[-1][2]
    del viewer


def test_notifications_can_be_switched_off_per_site(
    cron_client: TestClient, mock_server: str, mailer: CapturingMailer
) -> None:
    mailer.sent.clear()
    tid = target_id_of(cron_client)
    body = {"frequency": "daily", "notify": False, "url": f"{mock_server}/hardened"}
    cron_client.put(f"/api/v1/schedules/{tid}", json=body).raise_for_status()
    run_cron(cron_client)
    cron_client.put(f"/api/v1/schedules/{tid}", json={**body, "url": f"{mock_server}/plain"}).raise_for_status()
    make_due(cron_client)
    assert run_cron(cron_client)["alerts_sent"] == 0
    assert mailer.sent == []


def test_a_schedule_stops_when_the_plan_no_longer_includes_it(cron_client: TestClient, mock_server: str) -> None:
    tid = target_id_of(cron_client)
    cron_client.put(
        f"/api/v1/schedules/{tid}",
        json={"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"},
    ).raise_for_status()
    state = cron_client.app.state.s  # type: ignore[attr-defined]
    state.entitlements.plan_for_async = _free_plan  # simulate a downgrade
    summary = run_cron(cron_client)
    assert summary["scans_started"] == 0
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["frequency"] == "off"


async def _free_plan(_org: str):  # type: ignore[no-untyped-def]
    from app.billing.plans import FREE

    return FREE


def test_turning_a_schedule_off_removes_it(cron_client: TestClient) -> None:
    tid = target_id_of(cron_client)
    cron_client.put(f"/api/v1/schedules/{tid}", json={"frequency": "weekly", "notify": True}).raise_for_status()
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["frequency"] == "weekly"
    cron_client.put(f"/api/v1/schedules/{tid}", json={"frequency": "off"}).raise_for_status()
    assert cron_client.get("/api/v1/schedules").json()["items"][0]["frequency"] == "off"
    assert run_cron(cron_client)["due"] == 0


def test_changes_are_written_to_the_audit_log(cron_client: TestClient) -> None:
    tid = target_id_of(cron_client)
    cron_client.put(f"/api/v1/schedules/{tid}", json={"frequency": "weekly", "notify": True}).raise_for_status()
    events = cron_client.get("/api/v1/audit-events").json()["items"]
    assert any(e["event_type"] == "schedule.updated" for e in events)
