"""Finding fingerprints, per-host state across scans, and analyst triage."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.account import AuditEventRow
from app.repositories.scans import ScanRepository
from app.scanner.checks import run_checks
from app.scanner.fingerprint import fingerprint
from app.schemas.scan import Confidence, Finding, FindingStatus, Severity, TargetMetadata
from app.tests.conftest import signup
from app.tests.test_checks_and_scoring import make_result
from app.tests.test_db_and_reports import make_org, make_repo

API = "/api/v1"
HOST = "a.example"


def finding(finding_id: str, severity: Severity = Severity.LOW) -> Finding:
    return Finding(
        id=finding_id, title=finding_id, severity=severity, category="c", description="d", remediation="r"
    )


def scan_with(
    repo: ScanRepository,
    org: str,
    user: str,
    findings: list[Finding],
    *,
    host: str = HOST,
    off_origin: str | None = None,
) -> str:
    scan_id = repo.create_scan(org, user, f"https://{host}/", host)
    meta = TargetMetadata(requested_url=f"https://{host}/", host=host, off_origin_redirect=off_origin)
    repo.complete_scan(scan_id, findings, 90, "A", meta)
    return scan_id


def status_of(repo: ScanRepository, scan_id: str, org: str, finding_id: str) -> Finding:
    detail = repo.get_scan(scan_id, org)
    assert detail is not None
    return next(f for f in detail.findings if f.id == finding_id)


# --- identity and confidence ------------------------------------------------------------


def test_fingerprint_is_stable_per_host_and_check() -> None:
    assert fingerprint("A.example", "SS-1") == fingerprint("a.example", "SS-1")
    assert fingerprint("a.example", "SS-1") != fingerprint("b.example", "SS-1")
    assert fingerprint("a.example", "SS-1") != fingerprint("a.example", "SS-2")
    assert len(fingerprint("a.example", "SS-1")) == 32


def test_header_findings_are_high_confidence_and_signature_matches_are_not() -> None:
    findings, _ = run_checks(make_result())
    assert findings and all(f.confidence is Confidence.HIGH for f in findings)
    listing = make_result(body=b"<html><title>Index of /files</title></html>")
    dir_finding = next(f for f in run_checks(listing)[0] if f.id == "SS-DIR-001")
    assert dir_finding.confidence is Confidence.MEDIUM


# --- state across scans -----------------------------------------------------------------


def test_new_finding_is_open_and_keeps_its_fingerprint(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = scan_with(repo, org, user, [finding("SS-1")])
    second = scan_with(repo, org, user, [finding("SS-1")])
    a, b = status_of(repo, first, org, "SS-1"), status_of(repo, second, org, "SS-1")
    assert a.status is FindingStatus.OPEN and a.first_seen_at is not None
    assert a.fingerprint == b.fingerprint == fingerprint(HOST, "SS-1")
    assert b.first_seen_at == a.first_seen_at  # same issue, first seen once


def test_report_does_not_claim_an_open_finding_is_unchecked_once_two_scans_reported_it(db_url: str) -> None:
    from app.reporting import reports

    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = scan_with(repo, org, user, [finding("SS-1")])
    assert "seen in one scan so far" in reports.to_markdown(repo.get_scan(first, org))  # type: ignore[arg-type]
    second = scan_with(repo, org, user, [finding("SS-1")])
    for text in (
        reports.to_markdown(repo.get_scan(second, org)),  # type: ignore[arg-type]
        reports.to_html(repo.get_scan(second, org)),  # type: ignore[arg-type]
    ):
        assert "first seen" in text and "last seen" in text
        assert "not yet re-checked" not in text


def test_finding_is_resolved_only_when_a_later_scan_no_longer_reports_it(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = scan_with(repo, org, user, [finding("SS-1"), finding("SS-2")])
    assert status_of(repo, first, org, "SS-1").status is FindingStatus.OPEN
    scan_with(repo, org, user, [finding("SS-2")])
    assert status_of(repo, first, org, "SS-1").status is FindingStatus.RESOLVED
    assert status_of(repo, first, org, "SS-2").status is FindingStatus.OPEN
    third = scan_with(repo, org, user, [finding("SS-1"), finding("SS-2")])  # regression
    assert status_of(repo, third, org, "SS-1").status is FindingStatus.OPEN


def test_failed_and_redirected_scans_never_resolve_anything(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = scan_with(repo, org, user, [finding("SS-1")])
    failed = repo.create_scan(org, user, f"https://{HOST}/", HOST)
    repo.fail_scan(failed, "boom")
    scan_with(repo, org, user, [], off_origin="http://other.example/")
    assert status_of(repo, first, org, "SS-1").status is FindingStatus.OPEN


def test_human_decisions_survive_later_scans(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    first = scan_with(repo, org, user, [finding("SS-1")])
    fp = fingerprint(HOST, "SS-1")
    assert repo.set_finding_status(org, fp, FindingStatus.ACCEPTED_RISK, "internal tool", user)
    scan_with(repo, org, user, [])
    kept = status_of(repo, first, org, "SS-1")
    assert kept.status is FindingStatus.ACCEPTED_RISK and kept.status_note == "internal tool"
    scan_with(repo, org, user, [finding("SS-1")])
    assert status_of(repo, first, org, "SS-1").status is FindingStatus.ACCEPTED_RISK


def test_state_is_per_host_and_per_organization(db_url: str) -> None:
    repo = make_repo(db_url)
    org_a, user_a = make_org(db_url, "a@example.com")
    org_b, user_b = make_org(db_url, "b@example.com")
    scan_a = scan_with(repo, org_a, user_a, [finding("SS-1")])
    scan_with(repo, org_b, user_b, [])  # another organization scanning the same host
    scan_with(repo, org_a, user_a, [], host="other.example")  # another host
    assert status_of(repo, scan_a, org_a, "SS-1").status is FindingStatus.OPEN
    # Organization B cannot triage organization A's finding.
    assert not repo.set_finding_status(
        org_b, fingerprint(HOST, "SS-1"), FindingStatus.FALSE_POSITIVE, None, user_b
    )


# --- API --------------------------------------------------------------------------------


def run_scan(
    client: TestClient, mock_server: str, path: str = "plain", headers: dict[str, str] | None = None
) -> dict:  # type: ignore[type-arg]
    response = client.post(
        f"{API}/scans",
        json={"url": f"{mock_server}/{path}", "authorization_confirmed": True},
        headers=headers or {},
    )
    assert response.status_code == 202, response.text
    scan_id = response.json()["id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        detail = client.get(f"{API}/scans/{scan_id}", headers=headers or {}).json()
        if detail["status"] in ("completed", "failed"):
            return detail  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def member_client(owner: TestClient, org: str, email: str, role: str) -> TestClient:
    other = TestClient(owner.app)
    signup(other, email, f"{email} org")
    added = owner.post(f"{API}/organizations/{org}/members", json={"email": email, "role": role})
    assert added.status_code == 201, added.text
    other.headers["X-Organization-Id"] = org
    return other


def test_analyst_can_triage_and_the_change_is_visible_and_audited(
    local_client: TestClient, mock_server: str
) -> None:
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    detail = run_scan(local_client, mock_server)
    target = next(f for f in detail["findings"] if f["id"] == "SS-HDR-CSP-001")
    assert target["status"] == "open" and target["confidence"] == "high" and len(target["fingerprint"]) == 32

    analyst = member_client(local_client, org, "analyst@example.com", "SECURITY_ANALYST")
    url = f"{API}/findings/{target['fingerprint']}"
    assert analyst.patch(url, json={"status": "accepted_risk", "note": "  static site  "}).status_code == 204

    after = next(
        f
        for f in local_client.get(f"{API}/scans/{detail['id']}").json()["findings"]
        if f["id"] == "SS-HDR-CSP-001"
    )
    assert after["status"] == "accepted_risk" and after["status_note"] == "static site"

    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.audit._session() as session:
        events = session.scalars(
            select(AuditEventRow).where(AuditEventRow.event_type == "finding.status_changed")
        ).all()
    assert len(events) == 1 and events[0].resource_id == target["fingerprint"]


def test_only_roles_with_triage_permission_can_change_status(
    local_client: TestClient, mock_server: str
) -> None:
    org = local_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    fp = run_scan(local_client, mock_server)["findings"][0]["fingerprint"]
    for index, role in enumerate(["MEMBER", "VIEWER"]):
        client = member_client(local_client, org, f"low{index}@example.com", role)
        assert client.patch(f"{API}/findings/{fp}", json={"status": "false_positive"}).status_code == 403
    assert local_client.patch(f"{API}/findings/{fp}", json={"status": "false_positive"}).status_code == 204


def test_triage_input_is_validated_and_isolated(
    local_client: TestClient, mock_server: str, anon_client: TestClient
) -> None:
    fp = run_scan(local_client, mock_server)["findings"][0]["fingerprint"]
    assert local_client.patch(f"{API}/findings/{fp}", json={"status": "resolved"}).status_code == 422
    assert local_client.patch(f"{API}/findings/{fp}", json={"status": "nonsense"}).status_code == 422
    assert (
        local_client.patch(f"{API}/findings/{fp}", json={"status": "open", "note": "x" * 501}).status_code
        == 422
    )
    assert local_client.patch(f"{API}/findings/not-a-fingerprint", json={"status": "open"}).status_code == 404
    assert local_client.patch(f"{API}/findings/{'0' * 32}", json={"status": "open"}).status_code == 404
    assert anon_client.patch(f"{API}/findings/{fp}", json={"status": "open"}).status_code == 401

    other = TestClient(local_client.app)
    signup(other, "mallory@example.com", "Mallory Org")
    assert other.patch(f"{API}/findings/{fp}", json={"status": "false_positive"}).status_code == 404
    assert (
        local_client.get(f"{API}/scans/{run_scan(local_client, mock_server)['id']}").json()["findings"][0][
            "status"
        ]
        == "open"
    )


# --- migration of existing data ---------------------------------------------------------


def test_migration_backfills_fingerprints_and_states_from_history(db_url: str, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine, text

    from app.database.migrate import upgrade

    url = db_url
    engine = create_engine(url)
    with engine.begin() as conn:  # rebuild the schema as it was before this change
        if url.startswith("sqlite"):
            conn.execute(text("DROP TABLE IF EXISTS finding_states"))
        else:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    if url.startswith("sqlite"):
        import os

        engine.dispose()
        os.remove(url.removeprefix("sqlite:///"))
    upgrade(url, "0003")

    t0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id,email,password_hash,account_status,created_at,updated_at) "
                "VALUES ('u1','m@example.com','x','active',:t,:t)"
            ),
            {"t": t0},
        )
        conn.execute(
            text(
                "INSERT INTO organizations (id,name,slug,status,created_at,updated_at) "
                "VALUES ('o1','Org','org','active',:t,:t)"
            ),
            {"t": t0},
        )
        history = [
            ("s1", t0, ["SS-A", "SS-DIR-001"]),  # first scan: two findings
            ("s2", t0 + timedelta(days=1), ["SS-DIR-001"]),  # SS-A was fixed
        ]
        for scan_id, when, ids in history:
            conn.execute(
                text(
                    "INSERT INTO scans (id,organization_id,target_url,host,status,authorization_confirmed_at,"
                    "created_at,finished_at) VALUES (:id,'o1','https://a.example/','a.example','completed',:t,:t,:t)"
                ),
                {"id": scan_id, "t": when},
            )
            for position, finding_id in enumerate(ids):
                conn.execute(
                    text(
                        "INSERT INTO findings (scan_id,position,finding_id,title,severity,category,description,remediation) "
                        "VALUES (:s,:p,:f,'t','low','c','d','r')"
                    ),
                    {"s": scan_id, "p": position, "f": finding_id},
                )

    upgrade(url)  # to head

    with engine.connect() as conn:
        findings = conn.execute(
            text(
                "SELECT scan_id, finding_id, fingerprint, confidence FROM findings ORDER BY scan_id, position"
            )
        ).all()
        states = {
            row[0]: row
            for row in conn.execute(text("SELECT finding_id, status, resolved_at FROM finding_states")).all()
        }
    assert all(row[2] == fingerprint("a.example", row[1]) for row in findings)
    assert {row[1]: row[3] for row in findings}["SS-DIR-001"] == "medium"
    assert {row[1]: row[3] for row in findings}["SS-A"] == "high"
    assert states["SS-A"][1] == "resolved" and states["SS-A"][2] is not None
    assert states["SS-DIR-001"][1] == "open"
