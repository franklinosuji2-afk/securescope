"""The self-service client flow: sign up, confirm email, scan, read results, download PDF reports.

These tests run with email confirmation switched ON (most other tests switch it off) and focus on what
must never happen: a client reaching another client's sites, scans, results or reports.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select

from app.main import create_app
from app.models.scan import ReportRow, ScanRow
from app.tests.conftest import PASSWORD, CapturingMailer, signup, trust_host
from app.tests.test_finding_lifecycle import API, member_client, run_scan


def token_for(mailer: CapturingMailer, email: str, subject_part: str) -> str:
    for to, subject, body in reversed(mailer.sent):
        if to == email and subject_part in subject:
            return body.rsplit("token=", 1)[1].strip()
    raise AssertionError(f"no '{subject_part}' mail for {email}")


def confirm_email(client: TestClient, mailer: CapturingMailer, email: str) -> None:
    token = token_for(mailer, email, "Confirm")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200


def new_client(app_client: TestClient, mailer: CapturingMailer, email: str, *, verified: bool = True) -> TestClient:
    other = TestClient(app_client.app)
    signup(other, email, f"{email} workspace")
    if verified:
        confirm_email(other, mailer, email)
    return other


@pytest.fixture
def app_client(make_settings, mailer) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    settings = make_settings(
        require_verified_email=True, allow_private_targets=True, request_timeout_seconds=1.0
    )
    with TestClient(create_app(settings, mailer)) as client:
        yield client


@pytest.fixture
def alice(app_client: TestClient, mailer: CapturingMailer) -> Iterator[TestClient]:
    # Entered as a context manager so the app's event loop stays alive and background scans can finish.
    with TestClient(app_client.app) as client:
        signup(client, "alice@example.com", "alice@example.com workspace")
        confirm_email(client, mailer, "alice@example.com")
        trust_host(client, "127.0.0.1")
        yield client


@pytest.fixture
def bob(app_client: TestClient, mailer: CapturingMailer) -> Iterator[TestClient]:
    with TestClient(app_client.app) as client:
        signup(client, "bob@example.com", "bob@example.com workspace")
        confirm_email(client, mailer, "bob@example.com")
        yield client


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


# --- registration, email confirmation, login -------------------------------------------------------


def test_registering_sends_a_confirmation_link_and_starts_unconfirmed(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    body = signup(app_client, "new@example.com")
    assert body["email_verified"] is False
    to, subject, text = mailer.sent[-1]
    assert to == "new@example.com" and "Confirm" in subject
    assert "confirm your email address" in text and "token=" in text


def test_registering_twice_with_one_address_is_refused(app_client: TestClient) -> None:
    signup(app_client, "dup@example.com")
    again = TestClient(app_client.app).post(
        f"{API}/auth/register", json={"email": "DUP@example.com", "password": PASSWORD}
    )
    assert again.status_code == 409


def test_weak_passwords_are_refused(app_client: TestClient) -> None:
    response = app_client.post(f"{API}/auth/register", json={"email": "w@example.com", "password": "short"})
    assert response.status_code == 422


def test_dashboard_data_needs_a_confirmed_email(app_client: TestClient, mailer: CapturingMailer) -> None:
    client = new_client(app_client, mailer, "unconfirmed@example.com", verified=False)
    assert client.get(f"{API}/auth/me").status_code == 200  # can see who they are, and resend the link
    for method, path, payload in (
        ("get", "/targets", None),
        ("post", "/targets", {"hostname": "example.com"}),
        ("get", "/scans", None),
        ("post", "/scans", {"url": "https://example.com/", "authorization_confirmed": True}),
        ("get", "/overview", None),
    ):
        response = getattr(client, method)(f"{API}{path}", **({"json": payload} if payload else {}))
        assert response.status_code == 403, (path, response.text)
        assert "confirm your email" in response.json()["detail"]


def test_confirming_the_email_unlocks_the_dashboard(app_client: TestClient, mailer: CapturingMailer) -> None:
    client = new_client(app_client, mailer, "c@example.com", verified=False)
    assert client.get(f"{API}/targets").status_code == 403
    confirm_email(client, mailer, "c@example.com")
    assert client.get(f"{API}/targets").status_code == 200
    assert client.get(f"{API}/auth/me").json()["email_verified"] is True


def test_a_confirmation_link_works_once_and_a_forged_one_never(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    client = new_client(app_client, mailer, "once@example.com", verified=False)
    token = token_for(mailer, "once@example.com", "Confirm")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400
    assert client.post(f"{API}/auth/verify-email", json={"token": "x" * 43}).status_code == 400


def test_a_new_confirmation_link_can_be_requested(app_client: TestClient, mailer: CapturingMailer) -> None:
    client = new_client(app_client, mailer, "again@example.com", verified=False)
    before = len(mailer.sent)
    assert client.post(f"{API}/auth/resend-verification").status_code == 202
    assert len(mailer.sent) == before + 1


def test_login_logout_and_a_generic_error_for_bad_credentials(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    new_client(app_client, mailer, "login@example.com")
    visitor = TestClient(app_client.app)
    wrong = visitor.post(f"{API}/auth/login", json={"email": "login@example.com", "password": "wrong-password-x"})
    unknown = visitor.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # does not reveal which addresses have accounts
    ok = visitor.post(f"{API}/auth/login", json={"email": "login@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["email_verified"] is True
    visitor.headers["X-CSRF-Token"] = visitor.cookies.get("ss_csrf") or ""
    assert visitor.get(f"{API}/targets").status_code == 200
    assert visitor.post(f"{API}/auth/logout").status_code == 204
    assert visitor.get(f"{API}/targets").status_code == 401


def test_password_reset_by_email(app_client: TestClient, mailer: CapturingMailer) -> None:
    new_client(app_client, mailer, "reset@example.com")
    visitor = TestClient(app_client.app)
    assert visitor.post(f"{API}/auth/forgot-password", json={"email": "reset@example.com"}).status_code == 202
    # The same answer for an address that has no account.
    assert visitor.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 202
    token = token_for(mailer, "reset@example.com", "Reset")
    new_password = "a-brand-new-passphrase-1"
    assert visitor.post(f"{API}/auth/reset-password", json={"token": token, "password": new_password}).status_code == 200
    assert visitor.post(f"{API}/auth/reset-password", json={"token": token, "password": new_password}).status_code == 400
    old = visitor.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": PASSWORD})
    assert old.status_code == 401
    new = visitor.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": new_password})
    assert new.status_code == 200


# --- every protected endpoint needs a session ------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/targets"),
        ("post", "/targets"),
        ("delete", "/targets/abc"),
        ("get", "/scans"),
        ("post", "/scans"),
        ("get", "/scans/abc"),
        ("get", "/scans/abc/results"),
        ("get", "/scans/abc/report/pdf"),
        ("get", "/scans/abc/report/pdf/download"),
        ("patch", "/account/password"),
        ("delete", "/account"),
    ],
)
def test_signed_out_visitors_are_refused(app_client: TestClient, method: str, path: str) -> None:
    visitor = TestClient(app_client.app)
    response = getattr(visitor, method)(f"{API}{path}")
    assert response.status_code == 401, response.text


# --- scans, results, ownership ---------------------------------------------------------------------


def test_a_client_adds_a_site_scans_it_and_reads_the_results(
    alice: TestClient, mock_server: str
) -> None:
    scan = run_scan(alice, mock_server)
    assert scan["status"] == "completed"
    assert any(s["id"] == scan["id"] for s in alice.get(f"{API}/scans").json()["items"])
    results = alice.get(f"{API}/scans/{scan['id']}/results")
    assert results.status_code == 200
    body = results.json()
    assert body["risk_level"] in {"critical", "high", "medium", "low", "minimal"}
    assert body["risk_label"] and body["risk_summary"]
    assert sum(body["severity_counts"].values()) == len(body["findings"])
    first = next(f for f in body["findings"] if f["id"] == "SS-HDR-CSP-001")
    for field in ("severity", "affected_url", "description", "evidence", "remediation", "title"):
        assert first[field], field
    assert first["affected_url"].startswith("http://127.0.0.1")


def test_results_are_not_available_before_the_scan_finishes(alice: TestClient) -> None:
    state = alice.app.state.s  # type: ignore[attr-defined]
    me = alice.get(f"{API}/auth/me").json()
    scan_id = state.repo.create_scan(me["organizations"][0]["id"], me["id"], "http://127.0.0.1/", "127.0.0.1")
    assert alice.get(f"{API}/scans/{scan_id}/results").status_code == 409
    assert alice.get(f"{API}/scans/{scan_id}/report/pdf").status_code == 409


def test_one_client_cannot_see_start_or_delete_anything_of_another(
    alice: TestClient, bob: TestClient, mock_server: str
) -> None:
    scan = run_scan(alice, mock_server)
    sid = scan["id"]
    alice_target = alice.get(f"{API}/targets").json()["items"][0]["id"]
    link = alice.get(f"{API}/scans/{sid}/report/pdf").json()["url"]

    # Bob's own lists are empty, and every direct request for Alice's things looks like "not found".
    assert bob.get(f"{API}/scans").json()["total"] == 0
    assert bob.get(f"{API}/targets").json()["items"] == []
    for path in (f"/scans/{sid}", f"/scans/{sid}/results", f"/scans/{sid}/report/pdf", f"/scans/{sid}/report"):
        assert bob.get(f"{API}{path}").status_code == 404, path
    assert bob.get(f"{API}{link.removeprefix('/api/v1')}").status_code in (403, 404)
    assert bob.delete(f"{API}/scans/{sid}").status_code == 404
    assert bob.post(f"{API}/scans/{sid}/retry").status_code == 404
    assert bob.delete(f"{API}/targets/{alice_target}").status_code == 404
    # Naming Alice's organization does not help.
    alice_org = alice.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    assert bob.get(f"{API}/scans", headers={"X-Organization-Id": alice_org}).status_code == 403
    assert bob.get(f"{API}/scans/{sid}/results", headers={"X-Organization-Id": alice_org}).status_code == 403
    # Bob cannot start a scan of a site only Alice has verified.
    started = bob.post(f"{API}/scans", json={"url": f"{mock_server}/plain", "authorization_confirmed": True})
    assert started.status_code == 403
    # And Alice's data is untouched.
    assert alice.get(f"{API}/scans/{sid}").status_code == 200
    assert len(alice.get(f"{API}/targets").json()["items"]) == 1


# --- PDF reports -----------------------------------------------------------------------------------


def test_the_pdf_report_is_made_once_stored_and_downloaded_through_an_expiring_link(
    alice: TestClient, mock_server: str
) -> None:
    sid = run_scan(alice, mock_server)["id"]
    first = alice.get(f"{API}/scans/{sid}/report/pdf")
    assert first.status_code == 200
    link = first.json()
    assert link["report_id"].startswith("SSR-") and link["size_bytes"] > 1000
    assert "expires=" in link["url"] and "sig=" in link["url"]
    assert first.headers["cache-control"] == "no-store"

    download = alice.get(link["url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith(f'attachment; filename="{link["report_id"]}-')
    assert download.headers["cache-control"] == "private, no-store"
    assert download.content.startswith(b"%PDF-")
    text = pdf_text(download.content).lower()
    for expected in (link["report_id"], "securescope", "overall risk rating", "content-security-policy header is missing"):
        assert expected.lower() in text, expected

    # Asking again gives the same stored report with a new link; nothing is built twice.
    second = alice.get(f"{API}/scans/{sid}/report/pdf").json()
    assert second["report_id"] == link["report_id"]
    state = alice.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session() as session:
        assert session.scalar(select(func.count()).select_from(ReportRow)) == 1
    events = alice.get(f"{API}/audit-events").json()["items"]
    kinds = [e["event_type"] for e in events]
    assert "report.created" in kinds and "report.downloaded" in kinds


def test_download_links_are_bound_to_the_person_the_organization_and_the_report(
    alice: TestClient, bob: TestClient, mock_server: str
) -> None:
    sid = run_scan(alice, mock_server)["id"]
    link = alice.get(f"{API}/scans/{sid}/report/pdf").json()["url"]
    assert alice.get(link).status_code == 200

    # No session: refused, even though the link itself is genuine.
    assert TestClient(alice.app).get(link).status_code == 401
    # Another person in the same workspace cannot use a link issued to Alice.
    org = alice.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    colleague = member_client(alice, org, "colleague@example.com", "VIEWER")
    confirm_email(colleague, alice.app.state.s.auth.mailer, "colleague@example.com")  # type: ignore[attr-defined]
    assert colleague.get(link).status_code == 403
    # They can still ask for their own link, and viewers may download reports.
    own = colleague.get(f"{API}/scans/{sid}/report/pdf")
    assert own.status_code == 200 and colleague.get(own.json()["url"]).status_code == 200
    # Another client gets nothing.
    assert bob.get(link).status_code in (403, 404)

    # Tampering: a changed signature, expiry or report address is refused.
    base, query = link.split("?")
    params = dict(part.split("=") for part in query.split("&"))
    bad_sig = params["sig"][:-1] + ("0" if params["sig"][-1] != "0" else "1")
    assert alice.get(f"{base}?org={params['org']}&expires={params['expires']}&sig={bad_sig}").status_code == 403
    later = int(params["expires"]) + 3600
    assert alice.get(f"{base}?org={params['org']}&expires={later}&sig={params['sig']}").status_code == 403
    assert alice.get(f"{base}?org={params['org']}&expires={params['expires']}").status_code == 422
    other_scan = f"{API}/scans/{'0' * 32}/report/pdf/download?org={params['org']}&expires={params['expires']}&sig={params['sig']}"
    assert alice.get(other_scan).status_code == 404


def test_download_links_expire(alice: TestClient, mock_server: str) -> None:
    sid = run_scan(alice, mock_server)["id"]
    meta = alice.get(f"{API}/scans/{sid}/report/pdf").json()
    state = alice.app.state.s  # type: ignore[attr-defined]
    me = alice.get(f"{API}/auth/me").json()
    org = me["organizations"][0]["id"]
    # A link whose time is already up is refused, even with a correct signature.
    past = int(time.time()) - 5
    from app.services.reports import _signature

    sig = _signature(state.download_key, meta["report_id"], me["id"], org, past)
    expired = alice.get(f"{API}/scans/{sid}/report/pdf/download?org={org}&expires={past}&sig={sig}")
    assert expired.status_code == 403 and "expired" in expired.json()["detail"]
    # The lifetime of a fresh link is the configured one.
    from datetime import datetime

    remaining = datetime.fromisoformat(meta["expires_at"]).timestamp() - time.time()
    assert 0 < remaining <= state.settings.download_url_ttl_seconds + 2


def test_a_failed_or_unknown_scan_has_no_report(alice: TestClient) -> None:
    state = alice.app.state.s  # type: ignore[attr-defined]
    me = alice.get(f"{API}/auth/me").json()
    scan_id = state.repo.create_scan(me["organizations"][0]["id"], me["id"], "http://127.0.0.1/", "127.0.0.1")
    state.repo.fail_scan(scan_id, "Connection refused.")
    failed = alice.get(f"{API}/scans/{scan_id}/report/pdf")
    assert failed.status_code == 409 and "finished successfully" in failed.json()["detail"]
    assert alice.get(f"{API}/scans/{'f' * 32}/report/pdf").status_code == 404
    assert alice.get(f"{API}/scans/not-an-id!/report/pdf").status_code == 404


def test_a_corrupted_stored_report_is_never_served(alice: TestClient, mock_server: str) -> None:
    sid = run_scan(alice, mock_server)["id"]
    url = alice.get(f"{API}/scans/{sid}/report/pdf").json()["url"]
    state = alice.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session.begin() as session:
        row = session.scalars(select(ReportRow)).one()
        row.content = b"%PDF-tampered"
    assert alice.get(url).status_code == 500


def test_deleting_a_scan_deletes_its_report(alice: TestClient, mock_server: str) -> None:
    sid = run_scan(alice, mock_server)["id"]
    alice.get(f"{API}/scans/{sid}/report/pdf")
    assert alice.delete(f"{API}/scans/{sid}").status_code == 204
    state = alice.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session() as session:
        assert session.scalar(select(func.count()).select_from(ReportRow)) == 0


def test_old_scans_and_their_reports_are_removed_by_the_retention_job(
    alice: TestClient, mock_server: str
) -> None:
    sid = run_scan(alice, mock_server)["id"]
    alice.get(f"{API}/scans/{sid}/report/pdf")
    state = alice.app.state.s  # type: ignore[attr-defined]
    assert state.repo.delete_older_than(0) == 1
    with state.report_service.reports._session() as session:
        assert session.scalar(select(func.count()).select_from(ReportRow)) == 0
        assert session.scalar(select(func.count()).select_from(ScanRow)) == 0


# --- account settings ------------------------------------------------------------------------------


def test_changing_the_password_signs_out_other_devices_but_not_this_one(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    phone = new_client(app_client, mailer, "pw@example.com")
    laptop = TestClient(app_client.app)
    assert laptop.post(f"{API}/auth/login", json={"email": "pw@example.com", "password": PASSWORD}).status_code == 200
    laptop.headers["X-CSRF-Token"] = laptop.cookies.get("ss_csrf") or ""

    wrong = laptop.patch(f"{API}/account/password", json={"current_password": "nope-nope-nope-1", "new_password": "another-long-passphrase-2"})
    assert wrong.status_code == 400 and "current password" in wrong.json()["detail"]
    same = laptop.patch(f"{API}/account/password", json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 400
    short = laptop.patch(f"{API}/account/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422

    new_password = "another-long-passphrase-2"
    changed = laptop.patch(f"{API}/account/password", json={"current_password": PASSWORD, "new_password": new_password})
    assert changed.status_code == 204
    assert laptop.get(f"{API}/targets").status_code == 200  # this device stays signed in
    assert phone.get(f"{API}/targets").status_code == 401  # the other one is signed out
    assert mailer.sent[-1][0] == "pw@example.com" and "password was changed" in mailer.sent[-1][1]
    fresh = TestClient(app_client.app)
    assert fresh.post(f"{API}/auth/login", json={"email": "pw@example.com", "password": PASSWORD}).status_code == 401
    assert fresh.post(f"{API}/auth/login", json={"email": "pw@example.com", "password": new_password}).status_code == 200


def test_changing_the_password_is_rate_limited(app_client: TestClient, mailer: CapturingMailer) -> None:
    client = new_client(app_client, mailer, "limit@example.com")
    codes = [
        client.patch(
            f"{API}/account/password",
            json={"current_password": f"wrong-password-{i}", "new_password": "another-long-passphrase-2"},
        ).status_code
        for i in range(7)
    ]
    assert codes[:5] == [400] * 5 and codes[5:] == [429, 429]


def test_deleting_an_account_removes_its_data_and_nothing_else(
    alice: TestClient, bob: TestClient, mock_server: str, mailer: CapturingMailer
) -> None:
    sid = run_scan(alice, mock_server)["id"]
    alice.get(f"{API}/scans/{sid}/report/pdf")
    trust_host(bob, "bob-site.example")

    assert alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "nope"}).status_code == 400
    assert alice.request("DELETE", f"{API}/account", json={"password": "wrong-password-1", "confirm": "DELETE"}).status_code == 400
    assert alice.get(f"{API}/scans/{sid}").status_code == 200  # nothing happened yet

    gone = alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
    assert gone.status_code == 204
    assert alice.get(f"{API}/auth/me").status_code == 401
    assert TestClient(alice.app).post(f"{API}/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 401
    state = alice.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session() as session:
        assert session.scalar(select(func.count()).select_from(ScanRow)) == 0
        assert session.scalar(select(func.count()).select_from(ReportRow)) == 0
    assert "deleted" in mailer.sent[-1][1]
    # Bob is unaffected.
    assert [t["hostname"] for t in bob.get(f"{API}/targets").json()["items"]] == ["bob-site.example"]
    # The address can be used again to open a new account.
    assert TestClient(alice.app).post(f"{API}/auth/register", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 201


def test_a_sole_owner_of_a_shared_workspace_must_hand_over_first(
    alice: TestClient, mailer: CapturingMailer
) -> None:
    org = alice.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    teammate = member_client(alice, org, "mate@example.com", "VIEWER")
    blocked = alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
    assert blocked.status_code == 409 and "only owner" in blocked.json()["detail"]
    # A member can leave a shared workspace by deleting their own account; the workspace stays.
    assert teammate.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"}).status_code == 204
    assert alice.get(f"{API}/targets").status_code == 200
