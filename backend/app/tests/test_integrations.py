"""API tokens for CI and public score badges."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models.integration import ApiTokenRow
from app.repositories.integrations import MAX_TOKENS_PER_ORGANIZATION, BadgeReading
from app.services.badge import render_badge
from app.tests.conftest import signup, trust_host
from app.tests.test_tenancy import add_member, finished_scan, new_user, org_of

API = "/api/v1"


@pytest.fixture
def ci_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=1.0)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        yield client


class Runner:
    """Calls the API like a CI runner: the same app and event loop, but without the browser's cookies.

    (A second TestClient would run requests in a different event loop, and a scan started there would be
    cancelled when that loop ends.)"""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        saved = list(self._client.cookies.jar)
        self._client.cookies.clear()
        try:
            return getattr(self._client, method)(*args, **kwargs)
        finally:
            self._client.cookies.clear()
            for cookie in saved:
                self._client.cookies.jar.set_cookie(cookie)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("get", *args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("post", *args, **kwargs)


def bare(client: TestClient) -> Runner:
    return Runner(client)


def make_token(client: TestClient, name: str = "GitHub Actions") -> dict[str, Any]:
    response = client.post(f"{API}/api-tokens", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def wait_done(runner: Runner, token: str, scan_id: str) -> dict[str, Any]:
    deadline = time.time() + 15
    while time.time() < deadline:
        body = runner.get(f"{API}/ci/scans/{scan_id}", headers=bearer(token)).json()
        if body["status"] in ("completed", "failed"):
            return body  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


# --- API tokens: making, listing, removing ------------------------------------------------------------


def test_a_token_is_shown_once_and_only_its_digest_is_stored(ci_client: TestClient) -> None:
    created = make_token(ci_client)
    token = created["token"]
    assert token.startswith("ssk_") and len(token) > 40
    listing = ci_client.get(f"{API}/api-tokens").json()
    assert listing["available"] is True and listing["limit"] == MAX_TOKENS_PER_ORGANIZATION
    assert token not in str(listing) and listing["items"][0]["prefix"] == token[:8]
    state = ci_client.app.state.s  # type: ignore[attr-defined]
    with state.integrations._session() as session:
        row = session.scalar(select(ApiTokenRow))
        assert row.token_hash != token and token not in str(row.__dict__) and len(row.token_hash) == 64


def test_tokens_have_a_limit_and_a_name(ci_client: TestClient) -> None:
    for i in range(MAX_TOKENS_PER_ORGANIZATION):
        make_token(ci_client, f"token {i}")
    assert ci_client.post(f"{API}/api-tokens", json={"name": "one more"}).status_code == 409
    assert ci_client.post(f"{API}/api-tokens", json={"name": "   "}).status_code in (400, 422)


def test_a_free_workspace_sees_why_it_cannot_make_tokens(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(default_plan=None), mailer)) as client:
        signup(client, "free@example.com", "Free Org")
        assert client.get(f"{API}/api-tokens").json()["available"] is False
        response = client.post(f"{API}/api-tokens", json={"name": "x"})
        assert response.status_code == 403 and "Professional and Agency" in response.json()["detail"]


def test_only_owners_and_admins_manage_tokens(ci_client: TestClient) -> None:
    org = org_of(ci_client)
    headers = {"X-Organization-Id": org}
    for role, email in (
        ("SECURITY_ANALYST", "ana@example.com"),
        ("MEMBER", "mem@example.com"),
        ("VIEWER", "v@example.com"),
    ):
        other = new_user(ci_client, email)
        add_member(ci_client, org, email, role)
        assert other.get(f"{API}/api-tokens", headers=headers).status_code == 403
        assert other.post(f"{API}/api-tokens", json={"name": "x"}, headers=headers).status_code == 403
    admin = new_user(ci_client, "admin@example.com")
    add_member(ci_client, org, "admin@example.com", "ADMIN")
    assert admin.post(f"{API}/api-tokens", json={"name": "ci"}, headers=headers).status_code == 201


def test_a_revoked_token_stops_working_and_other_workspaces_cannot_revoke_it(ci_client: TestClient) -> None:
    created = make_token(ci_client)
    mallory = new_user(ci_client, "mallory@example.com")
    assert mallory.delete(f"{API}/api-tokens/{created['id']}").status_code == 404
    runner = bare(ci_client)
    assert (
        runner.get(f"{API}/ci/scans/abc", headers=bearer(created["token"])).status_code == 404
    )  # valid token
    assert ci_client.delete(f"{API}/api-tokens/{created['id']}").status_code == 204
    assert runner.get(f"{API}/ci/scans/abc", headers=bearer(created["token"])).status_code == 401
    events = [e["event_type"] for e in ci_client.get(f"{API}/audit-events").json()["items"]]
    assert "api_token.created" in events and "api_token.revoked" in events


# --- CI access -------------------------------------------------------------------------------------------


def test_a_token_starts_and_reads_a_scan_of_a_verified_site(ci_client: TestClient, mock_server: str) -> None:
    token = make_token(ci_client)["token"]
    runner = bare(ci_client)
    started = runner.post(f"{API}/ci/scans", json={"url": f"{mock_server}/plain"}, headers=bearer(token))
    assert started.status_code == 202, started.text
    done = wait_done(runner, token, started.json()["id"])
    assert done["status"] == "completed" and isinstance(done["score"], int) and done["grade"]
    assert done["findings"] and set(done["findings"][0]) == {"id", "severity", "title"}
    assert "/#/findings?scan=" in done["link"]
    # the same scan is in the owner's dashboard, started by the person who made the token
    assert ci_client.get(f"{API}/scans/{done['id']}").status_code == 200
    # evidence and descriptions are not part of the CI answer
    assert "evidence" not in str(done) and "remediation" not in str(done)
    assert ci_client.get(f"{API}/api-tokens").json()["items"][0]["last_used_at"] is not None


def test_a_token_cannot_scan_a_site_that_is_not_verified(ci_client: TestClient) -> None:
    token = make_token(ci_client)["token"]
    response = bare(ci_client).post(
        f"{API}/ci/scans", json={"url": "https://not-mine.example/"}, headers=bearer(token)
    )
    assert response.status_code == 403 and "not been verified" in response.json()["detail"]


def test_a_token_only_sees_scans_of_its_own_workspace(ci_client: TestClient, mock_server: str) -> None:
    scan_id = finished_scan(ci_client, mock_server)
    mallory = new_user(ci_client, "mallory@example.com")
    foreign = make_token(mallory)["token"]
    runner = bare(ci_client)
    assert runner.get(f"{API}/ci/scans/{scan_id}", headers=bearer(foreign)).status_code == 404
    mine = make_token(ci_client)["token"]
    assert runner.get(f"{API}/ci/scans/{scan_id}", headers=bearer(mine)).status_code == 200


@pytest.mark.parametrize(
    "header", [None, "Basic abc", "Bearer", "Bearer ssk_nonsense", "Bearer " + "x" * 500]
)
def test_missing_or_wrong_credentials_are_refused(ci_client: TestClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    response = bare(ci_client).post(f"{API}/ci/scans", json={"url": "https://x.example/"}, headers=headers)
    assert response.status_code == 401


def test_repeated_wrong_tokens_are_throttled(ci_client: TestClient) -> None:
    runner = bare(ci_client)
    codes = [
        runner.get(f"{API}/ci/scans/abc", headers=bearer(f"ssk_wrong{i}")).status_code for i in range(32)
    ]
    assert codes[:30] == [401] * 30 and codes[30:] == [429, 429]


def test_a_session_cookie_is_not_a_token_and_a_token_is_not_a_session(ci_client: TestClient) -> None:
    token = make_token(ci_client)["token"]
    assert ci_client.get(f"{API}/ci/scans/abc").status_code == 401  # cookies do not open the CI endpoints
    assert bare(ci_client).get(f"{API}/scans", headers=bearer(token)).status_code == 401
    assert bare(ci_client).get(f"{API}/api-tokens", headers=bearer(token)).status_code == 401


def test_a_token_stops_when_its_owner_loses_the_right_to_scan(
    ci_client: TestClient, mock_server: str
) -> None:
    org = org_of(ci_client)
    admin = new_user(ci_client, "admin@example.com")
    add_member(ci_client, org, "admin@example.com", "ADMIN")
    headers = {"X-Organization-Id": org}
    token = admin.post(f"{API}/api-tokens", json={"name": "ci"}, headers=headers).json()["token"]
    runner = bare(ci_client)
    assert runner.get(f"{API}/ci/scans/abc", headers=bearer(token)).status_code == 404  # works
    admin_id = admin.get(f"{API}/auth/me").json()["id"]
    ci_client.patch(
        f"{API}/organizations/{org}/members/{admin_id}", json={"role": "VIEWER"}
    ).raise_for_status()
    assert runner.get(f"{API}/ci/scans/abc", headers=bearer(token)).status_code == 401
    ci_client.delete(f"{API}/organizations/{org}/members/{admin_id}").raise_for_status()
    assert runner.get(f"{API}/ci/scans/abc", headers=bearer(token)).status_code == 401


def test_a_workspace_that_loses_the_plan_cannot_start_ci_scans(
    ci_client: TestClient, mock_server: str
) -> None:
    token = make_token(ci_client)["token"]
    from app.billing.plans import FREE

    async def free(_org: str):  # type: ignore[no-untyped-def]
        return FREE

    ci_client.app.state.s.entitlements.plan_for_async = free  # type: ignore[attr-defined]
    response = bare(ci_client).post(
        f"{API}/ci/scans", json={"url": f"{mock_server}/plain"}, headers=bearer(token)
    )
    assert response.status_code == 403 and "Professional and Agency" in response.json()["detail"]


# --- badges ----------------------------------------------------------------------------------------------


def badge_path(url: str) -> str:
    return url[url.index("/api/") :]


def enable_badge(client: TestClient, target_id: str, **extra: Any) -> dict[str, Any]:
    response = client.put(f"{API}/badges/{target_id}", json={"enabled": True, **extra})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def target_of(client: TestClient) -> str:
    return str(client.get(f"{API}/badges").json()["items"][0]["target_id"])


def test_badges_are_off_until_the_owner_turns_one_on(ci_client: TestClient) -> None:
    item = ci_client.get(f"{API}/badges").json()["items"][0]
    assert item["hostname"] == "127.0.0.1" and item["enabled"] is False and item["url"] is None


def test_a_badge_says_not_scanned_then_shows_the_latest_score(
    ci_client: TestClient, mock_server: str
) -> None:
    badge = enable_badge(ci_client, target_of(ci_client))
    path = badge_path(badge["url"])
    anyone = bare(ci_client)
    empty = anyone.get(path)
    assert empty.status_code == 200 and empty.headers["content-type"] == "image/svg+xml"
    assert "not scanned yet" in empty.text and "SecureScope" in empty.text
    scan_id = finished_scan(ci_client, mock_server)
    detail = ci_client.get(f"{API}/scans/{scan_id}").json()
    shown = anyone.get(path)
    assert f"{detail['score']}/100" in shown.text and detail["grade"] in shown.text
    assert "default-src 'none'" in shown.headers["content-security-policy"]
    assert shown.headers["cache-control"].startswith("public")
    assert "127.0.0.1" not in shown.text and "<script" not in shown.text  # nothing but the score


def test_turning_a_badge_off_or_renewing_it_kills_the_old_address(ci_client: TestClient) -> None:
    target = target_of(ci_client)
    first = badge_path(enable_badge(ci_client, target)["url"])
    anyone = bare(ci_client)
    assert anyone.get(first).status_code == 200
    again = enable_badge(ci_client, target)  # already on: nothing changes
    assert badge_path(again["url"]) == first
    renewed = badge_path(enable_badge(ci_client, target, renew=True)["url"])
    assert renewed != first
    old = anyone.get(first)
    assert old.status_code == 404 and "unavailable" in old.text and old.headers["cache-control"] == "no-store"
    assert anyone.get(renewed).status_code == 200
    off = ci_client.put(f"{API}/badges/{target}", json={"enabled": False}).json()
    assert off["enabled"] is False and off["url"] is None
    assert anyone.get(renewed).status_code == 404


@pytest.mark.parametrize("name", ["nope.svg", "x" * 40 + ".svg", "..%2Fetc.svg", "abc.png", "a.svg", ".svg"])
def test_unknown_badge_names_get_the_neutral_badge(ci_client: TestClient, name: str) -> None:
    response = bare(ci_client).get(f"{API}/badges/{name}")
    assert response.status_code in (404, 422) or "unavailable" in response.text
    assert "SecureScope" in response.text or response.status_code == 404


def test_only_site_managers_change_badges_and_other_workspaces_cannot(ci_client: TestClient) -> None:
    target = target_of(ci_client)
    org = org_of(ci_client)
    viewer = new_user(ci_client, "viewer@example.com")
    add_member(ci_client, org, "viewer@example.com", "VIEWER")
    headers = {"X-Organization-Id": org}
    assert viewer.get(f"{API}/badges", headers=headers).status_code == 200
    assert viewer.put(f"{API}/badges/{target}", json={"enabled": True}, headers=headers).status_code == 403
    mallory = new_user(ci_client, "mallory@example.com")
    assert mallory.put(f"{API}/badges/{target}", json={"enabled": True}).status_code == 404
    assert mallory.get(f"{API}/badges").json()["items"] == []


def test_a_site_that_is_not_verified_cannot_have_a_badge(ci_client: TestClient) -> None:
    created = ci_client.post(f"{API}/targets", json={"hostname": "unverified.example.com"}).json()
    assert ci_client.put(f"{API}/badges/{created['id']}", json={"enabled": True}).status_code == 404


def test_removing_the_site_removes_its_badge(ci_client: TestClient) -> None:
    target = target_of(ci_client)
    path = badge_path(enable_badge(ci_client, target)["url"])
    assert ci_client.delete(f"{API}/targets/{target}").status_code == 204
    assert bare(ci_client).get(path).status_code == 404


# --- the picture itself ---------------------------------------------------------------------------------


def test_the_badge_is_deterministic_and_escapes_everything() -> None:
    from datetime import UTC, datetime

    reading = BadgeReading(92, "A", datetime(2026, 10, 22, tzinfo=UTC))
    assert render_badge(reading) == render_badge(reading)
    assert "92/100 · A" in render_badge(reading) and "22 Oct 2026" in render_badge(reading)
    evil = render_badge(BadgeReading(5, '"><script>alert(1)</script>', None))
    assert "<script" not in evil and "&lt;script" in evil
    assert "not scanned yet" in render_badge(None) and "unavailable" in render_badge(None, available=False)
    assert "not proof of security" in render_badge(reading)  # said where a screen reader or hover finds it


def test_ci_results_leave_out_findings_the_team_triaged(ci_client: TestClient, mock_server: str) -> None:
    """A finding marked false positive or accepted risk must not fail a pipeline, or the team could never unblock it."""
    token = make_token(ci_client)["token"]
    runner = bare(ci_client)
    started = runner.post(f"{API}/ci/scans", json={"url": f"{mock_server}/plain"}, headers=bearer(token))
    done = wait_done(runner, token, started.json()["id"])
    before = {f["id"] for f in done["findings"]}
    assert len(before) >= 2
    own = ci_client.get(f"{API}/scans/{done['id']}").json()["findings"]
    false_positive, accepted = own[0], own[1]
    for finding, status in ((false_positive, "false_positive"), (accepted, "accepted_risk")):
        patched = ci_client.patch(f"{API}/findings/{finding['fingerprint']}", json={"status": status})
        assert patched.status_code == 204, patched.text
    after = runner.get(f"{API}/ci/scans/{done['id']}", headers=bearer(token)).json()
    ids = [f["id"] for f in after["findings"]]
    assert false_positive["id"] not in ids and accepted["id"] not in ids
    assert set(ids) == before - {false_positive["id"], accepted["id"]}
