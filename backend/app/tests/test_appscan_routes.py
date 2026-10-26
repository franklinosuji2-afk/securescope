"""App Scanning routes: the feature flag, permissions, workspace isolation, limits, accounting and honest results.

The vulnerability source is always a fake here. The default source in the application is `UnavailableSource`, so a
real scan with nothing injected must end Failed and must not be counted."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.appscan.vulns import Advisory, LookupResult, SourceInfo
from app.billing.plans import current_period
from app.main import create_app
from app.security.permissions import MATRIX, Permission, Role
from app.tests.canary import assert_no_canary, make_canary
from app.tests.conftest import signup
from app.tests.test_tenancy import add_member, new_user, org_of

API = "/api/v1/app"
LOCK = json.dumps(
    {
        "lockfileVersion": 3,
        "packages": {"": {"name": "x"}, "node_modules/lodash": {"version": "4.17.20"}},
    }
)
ADV = Advisory(
    "GHSA-aaaa-bbbb-cccc",
    "Prototype pollution",
    ("CVE-2021-23337",),
    "high",
    ("4.17.21",),
    ("https://github.com/advisories/GHSA-aaaa-bbbb-cccc",),
)


class Fake:
    max_batch = 100

    def __init__(self, table: dict[str, list[Advisory] | None] | None = None) -> None:
        self.table = table or {}

    def lookup(self, packages: Sequence[Any]) -> LookupResult:
        return LookupResult(
            [self.table.get(p.name, []) for p in packages], SourceInfo("fake-db", "1", "2026-10-26")
        )


def make_app(make_settings: Any, mailer: Any, **kw: Any) -> TestClient:
    settings = make_settings(app_scanning_enabled=kw.pop("enabled", True), **kw)
    return TestClient(create_app(settings, mailer))


@pytest.fixture
def app_on(make_settings, mailer):  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake({"lodash": [ADV]})  # type: ignore[attr-defined]
        yield client


@pytest.fixture
def app_free(make_settings, mailer):  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer, default_plan=None) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake({"lodash": [ADV]})  # type: ignore[attr-defined]
        yield client


def project(client: TestClient, name: str = "web", headers: dict[str, str] | None = None) -> str:
    response = client.post(f"{API}/projects", json={"name": name}, headers=headers or {})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def scan(client: TestClient, project_id: str, files: dict[str, str] | None = None, **kw: Any) -> Any:
    body = {
        "project_id": project_id,
        "kinds": ["dependency"],
        "files": [{"name": n, "content": c} for n, c in (files or {"package-lock.json": LOCK}).items()],
    }
    return client.post(f"{API}/scans", json=body, **kw)


def runs_used(client: TestClient) -> int:
    return int(client.get(f"{API}/overview").json()["usage"]["runs_used"])


# --- feature flag ------------------------------------------------------------------------------------------


def test_everything_answers_404_while_the_feature_is_off(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer, enabled=False) as client:
        signup(client, "owner@example.com", "Org")
        for method, path in [
            ("GET", "/overview"),
            ("GET", "/projects"),
            ("POST", "/projects"),
            ("POST", "/projects/abc/archive"),
            ("GET", "/scans"),
            ("POST", "/scans"),
            ("GET", "/scans/abc"),
        ]:
            assert client.request(method, f"{API}{path}", json={}).status_code == 404, path
    with make_app(make_settings, mailer, enabled=False) as anonymous:  # not even a sign-in is asked for
        assert anonymous.get(f"{API}/overview").status_code == 404


def test_signed_out_callers_are_refused_when_the_feature_is_on(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as anonymous:
        assert anonymous.get(f"{API}/overview").status_code in (401, 403)
        assert anonymous.post(f"{API}/scans", json={}).status_code in (401, 403)


# --- permissions ------------------------------------------------------------------------------------------


def test_each_role_may_do_exactly_what_the_matrix_allows(app_on: TestClient) -> None:
    org = org_of(app_on)
    headers = {"X-Organization-Id": org}
    pid = project(app_on)
    wrong: list[str] = []
    for role in [Role.VIEWER, Role.MEMBER, Role.SECURITY_ANALYST, Role.ADMIN]:
        email = f"{role.value.lower()}@example.com"
        person = new_user(app_on, email)
        assert add_member(app_on, org, email, role.value).status_code == 201
        calls: list[tuple[Permission, Callable[[TestClient], Any]]] = [
            (Permission.SCAN_READ, lambda c: c.get(f"{API}/overview", headers=headers)),
            (Permission.SCAN_READ, lambda c: c.get(f"{API}/scans/{'0' * 32}", headers=headers)),
            (
                Permission.SCAN_CREATE,
                lambda c: c.post(f"{API}/projects", json={"name": f"p-{email}"}, headers=headers),
            ),
            (Permission.SCAN_CREATE, lambda c: scan(c, pid, headers=headers)),
        ]
        for permission, call in calls:
            status = call(person).status_code
            allowed = permission in MATRIX[role]
            if allowed and status == 403:
                wrong.append(f"{role.value} refused")
            if not allowed and status != 403:
                wrong.append(f"{role.value} got {status}")
    assert wrong == []


# --- workspace isolation --------------------------------------------------------------------------------------


def test_another_workspace_cannot_see_or_touch_projects_and_scans(app_on: TestClient) -> None:
    pid = project(app_on)
    sid = scan(app_on, pid).json()["id"]
    other = new_user(app_on, "other@example.com")
    other.app.state.s.app_source = app_on.app.state.s.app_source  # type: ignore[attr-defined]
    assert other.get(f"{API}/scans/{sid}").status_code == 404
    assert other.post(f"{API}/projects/{pid}/archive").status_code == 404
    assert scan(other, pid).status_code == 404
    assert other.get(f"{API}/scans?project_id={pid}").json()["items"] == []
    assert other.get(f"{API}/projects").json()["items"] == []
    # Naming the owner's workspace without being a member is refused too.
    org = org_of(app_on)
    headers = {"X-Organization-Id": org}
    assert other.get(f"{API}/scans/{sid}", headers=headers).status_code in (403, 404)
    assert other.get(f"{API}/projects", headers=headers).status_code in (403, 404)
    assert app_on.get(f"{API}/scans/{sid}").status_code == 200  # untouched


def test_malformed_ids_are_404_not_server_errors(app_on: TestClient) -> None:
    for bad in ["../x", "a b", "x" * 100, "%00", "a;b"]:
        assert app_on.get(f"{API}/scans/{bad}").status_code == 404
        assert app_on.post(f"{API}/projects/{bad}/archive").status_code == 404
    assert app_on.get(f"{API}/scans?project_id=%27%20OR%201=1--").status_code == 404


# --- scanning and honest results -------------------------------------------------------------------------------


def test_a_scan_with_a_known_vulnerability_is_completed_with_findings(app_on: TestClient) -> None:
    response = scan(app_on, project(app_on))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed" and body["result"] == "completed_findings"
    assert body["counts"]["high"] == 1
    assert body["findings"][0]["package_name"] == "lodash"
    assert body["findings"][0]["fixed_versions"] == ["4.17.21"]
    assert body["limitations"], "the limitations block is always present"
    assert runs_used(app_on) == 1


def test_a_clean_scan_says_no_findings_from_these_checks_not_secure(app_on: TestClient) -> None:
    app_on.app.state.s.app_source = Fake()  # type: ignore[attr-defined]
    body = scan(app_on, project(app_on)).json()
    assert body["result"] == "completed_no_findings"
    text = body["result_text"].lower()
    assert "selected checks" in text and "secure" not in text


def test_the_default_source_is_unavailable_so_the_run_fails_and_is_not_counted(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as client:
        signup(client, "owner@example.com", "Org")
        body = scan(client, project(client)).json()
        assert body["status"] == "failed" and body["result"] == "scanner_error"
        assert body["findings"] == []
        assert runs_used(client) == 0


def test_an_outage_is_never_reported_as_clean(app_on: TestClient) -> None:
    app_on.app.state.s.app_source = Fake({"lodash": None})  # type: ignore[attr-defined]
    body = scan(app_on, project(app_on)).json()
    assert body["status"] in ("incomplete", "failed")
    assert body["result"] != "completed_no_findings"


def test_no_score_or_grade_anywhere(app_on: TestClient) -> None:
    pid = project(app_on)
    sid = scan(app_on, pid).json()["id"]
    texts = [
        app_on.get(f"{API}/scans/{sid}").text,
        app_on.get(f"{API}/scans").text,
        app_on.get(f"{API}/overview").text,
        app_on.get(f"{API}/projects").text,
    ]
    for text in texts:
        assert '"score"' not in text and '"grade"' not in text


def test_unsupported_entries_are_reported_and_the_scan_is_incomplete(app_on: TestClient) -> None:
    body = scan(app_on, project(app_on), {"requirements.txt": "flask>=2\nlodash==1.0\n"}).json()
    assert body["status"] == "incomplete"
    assert body["checks_skipped"]


# --- invalid input is refused and not counted ---------------------------------------------------------------------


def test_invalid_requests_are_refused_and_never_counted(app_free: TestClient) -> None:
    pid = project(app_free)
    cases: list[Any] = [
        scan(app_free, pid, {"evil.sh": "rm -rf /"}),
        scan(app_free, pid, {"package-lock.json": "{not json"}),
        scan(app_free, pid, {"package-lock.json": ""}),
        scan(app_free, pid, {"package.json": json.dumps({"name": "x"})}),  # nothing checkable
        app_free.post(f"{API}/scans", json={"project_id": pid, "kinds": ["sast"], "files": []}),
        app_free.post(f"{API}/scans", json={"project_id": pid, "kinds": ["dependency"], "files": []}),
        app_free.post(f"{API}/scans", content=b"not json", headers={"content-type": "application/json"}),
    ]
    for response in cases:
        assert 400 <= response.status_code < 500, response.text
    assert runs_used(app_free) == 0
    assert app_free.get(f"{API}/scans").json()["items"] == []


def test_duplicate_file_names_are_refused(app_on: TestClient) -> None:
    body = {
        "project_id": project(app_on),
        "kinds": ["dependency"],
        "files": [{"name": "package-lock.json", "content": LOCK}] * 2,
    }
    assert app_on.post(f"{API}/scans", json=body).status_code == 422


def test_an_oversized_body_is_413_and_nothing_is_stored(app_free: TestClient) -> None:
    pid = project(app_free)
    huge = {
        "project_id": pid,
        "kinds": ["dependency"],
        "files": [{"name": "requirements.txt", "content": "a" * (7 * 1024 * 1024)}],
    }
    assert app_free.post(f"{API}/scans", json=huge).status_code == 413
    assert runs_used(app_free) == 0


def test_unknown_fields_and_script_like_content_are_not_executed_or_echoed(app_on: TestClient) -> None:
    canary = make_canary()
    pid = project(app_on)
    reqs = f"lodash==1.0\n--index-url https://{canary}.example/simple\n$(touch /tmp/pwned)==1\n"
    response = scan(app_on, pid, {"requirements.txt": reqs})
    assert_no_canary(canary, response.text)
    assert_no_canary(canary, app_on.get(f"{API}/scans").text)


# --- limits and accounting ------------------------------------------------------------------------------------


def test_free_plan_project_cap_gives_403(app_free: TestClient) -> None:
    project(app_free, "one")
    assert app_free.post(f"{API}/projects", json={"name": "two"}).status_code == 403


def test_duplicate_project_names_conflict(app_on: TestClient) -> None:
    project(app_on, "same")
    assert app_on.post(f"{API}/projects", json={"name": "same"}).status_code == 409
    assert app_on.post(f"{API}/projects", json={"name": "  "}).status_code == 422


def test_the_monthly_allowance_stops_the_sixth_free_run(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer, default_plan=None, app_scans_per_project_per_hour=100) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake({"lodash": [ADV]})  # type: ignore[attr-defined]
        pid = project(client)
        for _ in range(5):
            assert scan(client, pid).status_code == 201
        assert scan(client, pid).status_code == 403
        assert runs_used(client) == 5


def test_the_hourly_limit_per_project_gives_429(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer, app_scans_per_project_per_hour=2) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake()  # type: ignore[attr-defined]
        pid = project(client)
        assert scan(client, pid).status_code == 201
        assert scan(client, pid).status_code == 201
        assert scan(client, pid).status_code == 429


def test_a_retry_with_the_same_idempotency_key_is_not_charged_twice(app_free: TestClient) -> None:
    pid = project(app_free)
    first = scan(app_free, pid, headers={"Idempotency-Key": "abc-123"})
    again = scan(app_free, pid, headers={"Idempotency-Key": "abc-123"})
    assert first.status_code == 201 and again.status_code == 201
    assert again.json()["id"] == first.json()["id"] and again.json()["replayed"] is True
    assert runs_used(app_free) == 1


def test_an_idempotency_key_cannot_be_reused_for_another_project(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake()  # type: ignore[attr-defined]
        a, b = project(client, "a"), project(client, "b")
        assert scan(client, a, headers={"Idempotency-Key": "k1"}).status_code == 201
        assert scan(client, b, headers={"Idempotency-Key": "k1"}).status_code == 409


def test_an_archived_project_cannot_be_scanned(app_on: TestClient) -> None:
    pid = project(app_on)
    assert app_on.post(f"{API}/projects/{pid}/archive").status_code == 204
    assert scan(app_on, pid).status_code == 404
    assert app_on.get(f"{API}/projects").json()["items"] == []


def test_a_defect_in_the_source_ends_the_run_failed_without_leaking(app_on: TestClient) -> None:
    secret = make_canary()

    class Boom:
        max_batch = 10

        def lookup(self, packages: Sequence[Any]) -> LookupResult:
            raise RuntimeError(f"boom {secret}")

    app_on.app.state.s.app_source = Boom()  # type: ignore[attr-defined]
    response = scan(app_on, project(app_on))
    assert response.json()["status"] == "failed"
    assert_no_canary(secret, response.text)
    assert runs_used(app_on) == 0


def test_overview_reports_limits_and_ci_token_rule(app_free: TestClient) -> None:
    free = app_free.get(f"{API}/overview").json()
    assert free["ci_tokens_available"] is False
    assert free["usage"]["runs_limit"] == 5 and free["usage"]["projects_limit"] == 1
    assert "package-lock.json" in free["supported_files"]


def test_audit_events_carry_ids_only(app_on: TestClient) -> None:
    pid = project(app_on)
    sid = scan(app_on, pid).json()["id"]
    events = app_on.get("/api/v1/audit-events").json()
    text = json.dumps(events)
    for name in ("app_project.created", "app_scan.created", "app_scan.finished"):
        assert name in text
    assert "lodash" not in text and sid in text


def test_a_chunked_body_over_the_limit_is_413_even_without_a_declared_length(app_free: TestClient) -> None:
    pid = project(app_free)
    chunk = b" " * (1024 * 1024)

    def body() -> Any:
        yield b'{"project_id": "' + pid.encode() + b'", "pad": "'
        for _ in range(7):
            yield chunk
        yield b'"}'

    response = app_free.post(f"{API}/scans", content=body(), headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert runs_used(app_free) == 0


def test_an_unexpected_defect_in_the_pipeline_fails_the_run_and_does_not_leak(
    app_on: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = make_canary()

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"defect {secret}")

    monkeypatch.setattr("app.api.v1.app_scans.run_dependency_scan", broken)
    response = scan(app_on, project(app_on))
    assert response.status_code == 201 and response.json()["status"] == "failed"
    assert_no_canary(secret, response.text)
    assert runs_used(app_on) == 0


def test_starting_the_app_interrupts_runs_left_unfinished_and_does_not_count_them(
    make_settings: Any, mailer: Any
) -> None:
    settings = make_settings(app_scanning_enabled=True, default_plan=None)
    app = create_app(settings, mailer)
    with TestClient(app) as client:
        signup(client, "owner@example.com", "Org")
        pid = project(client)
        state = client.app.state.s  # type: ignore[attr-defined]
        org = org_of(client)
        period_start, _ = current_period(datetime.now(UTC))
        run = state.app_scans.accept_run(
            org,
            pid,
            None,
            ["dependency"],
            [],
            5,
            period_start,
            100,
        ).scan_id
        assert state.app_scans.get_run(org, run).status == "queued"
    with TestClient(app) as again:  # a restart
        again.headers.update(client.headers)
        again.cookies.update(client.cookies)
        assert again.get(f"{API}/scans/{run}").json()["result"] == "interrupted"
        assert runs_used(again) == 0
