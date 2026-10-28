"""App Scanning CI tokens: scopes, isolation between Web and App endpoints, and authenticated submissions.

Every critical boundary has a negative test here (scope, plan, feature flag, expiry, revocation, workspace,
project, role, size, secrets, idempotency, per-token limit)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.appscan.submission import SubmissionRejected, parse_submission
from app.billing.plans import FREE
from app.main import create_app
from app.models.app_scan import AppFindingRow, AppScanRow
from app.models.integration import ApiTokenRow
from app.tests.canary import assert_no_canary, capture_logs, make_canary
from app.tests.conftest import signup
from app.tests.test_integrations import bare, bearer
from app.tests.test_tenancy import add_member, new_user, org_of

API = "/api/v1"
APP = f"{API}/app"
SUBMIT = f"{APP}/ci/submissions"


def doc(project_id: str, **kw: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": 1,
        "project_id": project_id,
        "checks": [
            {"kind": "sast", "status": "ran", "tool": {"name": "semgrep", "version": "1.0"}},
            {"kind": "secrets", "status": "ran", "tool": {"name": "gitleaks", "version": "8.0"}},
        ],
        "findings": [
            {
                "kind": "sast",
                "rule_id": "py.sql-injection",
                "severity": "high",
                "confidence": "medium",
                "path": "src/db.py",
                "line": 12,
                "title": "SQL built from input",
                "message": "Use parameters.",
            }
        ],
    }
    body.update(kw)
    return body


def make_app(make_settings: Any, mailer: Any, **kw: Any) -> TestClient:
    return TestClient(create_app(make_settings(app_scanning_enabled=kw.pop("enabled", True), **kw), mailer))


def new_project(client: TestClient, headers: dict[str, str] | None = None) -> str:
    r = client.post(f"{APP}/projects", json={"name": "svc"}, headers=headers or {})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def make_token(client: TestClient, scope: str, headers: dict[str, str] | None = None) -> Any:
    return client.post(
        f"{API}/api-tokens", json={"name": f"{scope}-ci", "scope": scope}, headers=headers or {}
    )


def submit(client: TestClient, token: str, body: Any, key: str = "run-1") -> Any:
    return bare(client).post(
        SUBMIT,
        content=json.dumps(body),
        headers={**bearer(token), "Idempotency-Key": key, "Content-Type": "application/json"},
    )


@pytest.fixture
def env(make_settings, mailer):  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as client:
        signup(client, "owner@example.com", "Org")
        pid = new_project(client)
        app_token = make_token(client, "app").json()["token"]
        web_token = make_token(client, "web").json()["token"]
        yield client, pid, app_token, web_token


def engine(client: TestClient) -> Any:
    return client.app.state.s.engine  # type: ignore[attr-defined]


def rows(client: TestClient, model: Any) -> list[Any]:
    with engine(client).connect() as conn:
        return list(conn.execute(select(model)).all())


def dump_tables(client: TestClient, *tables: str) -> str:
    with engine(client).connect() as conn:
        return "".join(str(conn.execute(text(f"select * from {t}")).all()) for t in tables)


def anon(client: TestClient, method: str, path: str, **kw: Any) -> Any:
    if method.upper() == "GET":
        kw.pop("json", None)
    return bare(client)._call(method.lower(), path, **kw)


def app_operations(client: TestClient) -> list[tuple[str, str]]:
    return [
        (m.upper(), p)
        for p, ops in client.app.openapi()["paths"].items()  # type: ignore[attr-defined]
        if p.startswith("/api/v1/app")
        for m in ops
        if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    ]


def fill(path: str) -> str:
    return path.replace("{project_id}", "x").replace("{scan_id}", "x").replace("{id}", "x")


# --- 1, 2: existing web tokens keep their behaviour and gain nothing ---------------------------------------


def test_a_default_token_is_a_web_token_with_no_expiry(env) -> None:  # type: ignore[no-untyped-def]
    client, _pid, _app_token, _web = env
    created = client.post(f"{API}/api-tokens", json={"name": "legacy-style"}).json()
    assert created["scope"] == "web" and created["expires_at"] is None
    listed = client.get(f"{API}/api-tokens").json()["items"]
    assert {t["scope"] for t in listed} == {"web", "app"}


def test_web_token_still_reaches_the_web_ci_routes(env) -> None:  # type: ignore[no-untyped-def]
    client, _pid, _app, web = env
    assert bare(client).get(f"{API}/ci/scans/abc", headers=bearer(web)).status_code == 404  # authenticated


# --- 3: a web token is refused on every App endpoint ---------------------------------------------------------


def test_web_token_is_refused_on_every_app_endpoint(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, _app, web = env
    ops = app_operations(client)
    assert len(ops) >= 8
    for method, path in ops:
        r = anon(client, method, fill(path), headers={**bearer(web), "Idempotency-Key": "k"}, json={})
        assert r.status_code in (401, 403), (method, path, r.status_code)
    assert submit(client, web, doc(pid)).status_code == 401


# --- 4: an app token is refused on every Web endpoint ------------------------------------------------------


def test_app_token_is_refused_on_web_endpoints(env) -> None:  # type: ignore[no-untyped-def]
    client, _pid, app_token, _web = env
    runner = bare(client)
    assert runner.get(f"{API}/ci/scans/abc", headers=bearer(app_token)).status_code == 401
    assert (
        runner.post(
            f"{API}/ci/scans", json={"url": "https://example.com"}, headers=bearer(app_token)
        ).status_code
        == 401
    )
    for method, path in [
        ("GET", f"{API}/scans"),
        ("GET", f"{API}/api-tokens"),
        ("POST", f"{API}/api-tokens"),
        ("GET", f"{APP}/overview"),
        ("GET", f"{APP}/projects"),
    ]:
        r = anon(
            client,
            method,
            path,
            headers=bearer(app_token),
            **({"json": {"name": "x"}} if method == "POST" else {}),
        )
        assert r.status_code == 401, (method, path, r.status_code)


# --- 5, 6: plan eligibility is decided on the server --------------------------------------------------------


def test_free_cannot_create_an_app_token(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer, default_plan=None) as client:
        signup(client, "o@example.com", "Org")
        r = make_token(client, "app")
        assert r.status_code == 403
        assert "token" not in r.json()


def test_an_eligible_plan_can_create_an_app_token_and_sees_it_once(env) -> None:  # type: ignore[no-untyped-def]
    client, _pid, app_token, _web = env
    assert app_token.startswith("ssa_") and not app_token.startswith("ssk_")  # old code cannot read it
    for t in client.get(f"{API}/api-tokens").json()["items"]:
        assert "token" not in t and "hash" not in json.dumps(t).lower()
    created = make_token(client, "app").json()
    assert created["scope"] == "app" and created["expires_at"] is not None
    stored = {r.token_hash for r in rows(client, ApiTokenRow)}
    assert hashlib.sha256(created["token"].encode()).hexdigest() in stored
    assert created["token"] not in stored


def test_a_plan_downgrade_stops_existing_app_tokens(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _web = env

    async def free(_org: str):  # type: ignore[no-untyped-def]
        return FREE

    assert submit(client, app_token, doc(pid), "ok-1").status_code == 201
    client.app.state.s.entitlements.plan_for_async = free
    assert submit(client, app_token, doc(pid), "ok-2").status_code == 401


def test_an_unknown_scope_is_refused(env) -> None:  # type: ignore[no-untyped-def]
    client, *_ = env
    assert client.post(f"{API}/api-tokens", json={"name": "x", "scope": "admin"}).status_code == 422


# --- 7: the feature flag closes everything, even for a valid token -------------------------------------------


def test_flag_off_blocks_app_routes_and_app_token_creation(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as on:
        signup(on, "owner@example.com", "Org")
        pid = new_project(on)
        token = make_token(on, "app").json()["token"]
    with make_app(make_settings, mailer, enabled=False) as off:
        signup(off, "second@example.com", "Org Two")
        assert submit(off, token, doc(pid)).status_code == 404
        assert bare(off).get(f"{APP}/overview", headers=bearer(token)).status_code == 404
        assert off.get(f"{APP}/overview").status_code == 404  # signed-in session
        assert bare(off).get(f"{APP}/overview").status_code == 404  # anonymous
        assert make_token(off, "app").status_code == 404


# --- 8: revoked and expired tokens -------------------------------------------------------------------------


def test_a_revoked_token_stops_immediately(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _web = env
    assert submit(client, app_token, doc(pid), "a").status_code == 201
    token_id = next(t["id"] for t in client.get(f"{API}/api-tokens").json()["items"] if t["scope"] == "app")
    client.delete(f"{API}/api-tokens/{token_id}").raise_for_status()
    assert submit(client, app_token, doc(pid), "b").status_code == 401


def test_an_expired_token_is_refused(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _web = env
    with engine(client).begin() as conn:
        conn.execute(
            update(ApiTokenRow)
            .where(ApiTokenRow.scope == "app")
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    r = submit(client, app_token, doc(pid))
    assert r.status_code == 401
    assert r.json()["detail"] == submit(client, "ssk_" + "0" * 40, doc(pid), "u").json()["detail"]


# --- 9: workspace and project isolation -----------------------------------------------------------------


def test_a_token_cannot_submit_to_another_workspaces_project(env) -> None:  # type: ignore[no-untyped-def]
    client, _pid, app_token, _web = env
    other = new_user(client, "other@example.com")
    other_pid = new_project(other)
    r = submit(client, app_token, doc(other_pid))
    assert r.status_code == 404
    assert r.json()["detail"] == submit(client, app_token, doc("nonexistent"), "z").json()["detail"]
    assert rows(client, AppScanRow) == []


def test_an_archived_project_takes_no_submissions(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _web = env
    client.post(f"{APP}/projects/{pid}/archive").raise_for_status()
    assert submit(client, app_token, doc(pid)).status_code == 404


# --- 10: roles ---------------------------------------------------------------------------------------------


def test_a_token_stops_when_its_owner_can_no_longer_start_scans(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, _a, _w = env
    org = org_of(client)
    admin = new_user(client, "admin@example.com")
    add_member(client, org, "admin@example.com", "ADMIN")
    token = make_token(admin, "app", {"X-Organization-Id": org}).json()["token"]
    assert submit(client, token, doc(pid), "r1").status_code == 201
    admin_id = admin.get(f"{API}/auth/me").json()["id"]
    client.patch(f"{API}/organizations/{org}/members/{admin_id}", json={"role": "VIEWER"}).raise_for_status()
    assert submit(client, token, doc(pid), "r2").status_code == 401


def test_only_owners_and_admins_create_app_tokens(env) -> None:  # type: ignore[no-untyped-def]
    client, *_ = env
    org = org_of(client)
    for role in ("MEMBER", "VIEWER", "SECURITY_ANALYST"):
        user = new_user(client, f"{role.lower()}@example.com")
        add_member(client, org, f"{role.lower()}@example.com", role)
        assert make_token(user, "app", {"X-Organization-Id": org}).status_code == 403, role


# --- 11: invalid, oversized and secret-bearing submissions -------------------------------------------------


def test_missing_idempotency_key_is_refused(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    r = bare(client).post(SUBMIT, json=doc(pid), headers=bearer(app_token))
    assert r.status_code == 400


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d.update(unexpected="x"),
        lambda d: d.update(checks=[]),
        lambda d: d["findings"][0].update(severity="catastrophic"),
        lambda d: d["findings"][0].update(path="../../etc/passwd"),
        lambda d: d["findings"][0].update(path="/etc/passwd"),
        lambda d: d.update(findings=d["findings"] * 5001),
    ],
)
def test_invalid_submissions_are_refused_before_anything_is_stored(env, mutate) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    body = doc(pid)
    mutate(body)
    r = submit(client, app_token, body)
    assert r.status_code in (413, 422), r.text
    assert rows(client, AppScanRow) == []


def test_not_json_is_a_400(env) -> None:  # type: ignore[no-untyped-def]
    client, _p, app_token, _w = env
    r = bare(client).post(SUBMIT, content=b"{nope", headers={**bearer(app_token), "Idempotency-Key": "k"})
    assert r.status_code == 400


def test_oversized_bodies_are_refused_declared_or_streamed(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    big = doc(pid)
    big["findings"][0]["message"] = "x" * (5 * 1024 * 1024)
    assert submit(client, app_token, big).status_code == 413

    def chunks() -> Iterator[bytes]:
        for _ in range(6):
            yield b" " * (1024 * 1024)

    r = bare(client).post(SUBMIT, content=chunks(), headers={**bearer(app_token), "Idempotency-Key": "k2"})
    assert r.status_code == 413
    assert rows(client, AppScanRow) == []


def test_a_secret_in_a_submission_is_refused_with_a_fixed_message_and_never_stored_or_logged(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    canary = make_canary()
    body = doc(pid)
    body["findings"][0]["message"] = f"found {canary} in config"
    handler, lines = capture_logs()
    logging.getLogger().addHandler(handler)
    try:
        r = submit(client, app_token, body)
    finally:
        logging.getLogger().removeHandler(handler)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "contains_secret"
    assert_no_canary(canary, r.text, lines)
    assert rows(client, AppScanRow) == []
    dump = dump_tables(client, "audit_events")
    assert_no_canary(canary, dump)


# --- 12: retries ---------------------------------------------------------------------------------------------


def usage(client: TestClient) -> int:
    return int(client.get(f"{APP}/overview").json()["usage"]["runs_used"])


def test_a_retry_with_the_same_key_creates_nothing_and_costs_nothing(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    first = submit(client, app_token, doc(pid), "pipeline-77")
    assert first.status_code == 201
    before = usage(client)
    again = submit(client, app_token, doc(pid), "pipeline-77")
    assert again.status_code in (200, 201) and again.json()["id"] == first.json()["id"]
    assert again.json().get("replayed") is True
    assert usage(client) == before == 1
    assert len(rows(client, AppScanRow)) == 1
    assert len(rows(client, AppFindingRow)) == 1


def test_a_new_key_is_a_new_run(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    a = submit(client, app_token, doc(pid), "k-a").json()["id"]
    b = submit(client, app_token, doc(pid), "k-b").json()["id"]
    assert a != b and usage(client) == 2


def test_a_ci_key_cannot_collide_with_a_browser_key(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    up = client.post(
        f"{APP}/scans",
        json={"project_id": pid, "kinds": ["dependency"], "files": []},
        headers={"Idempotency-Key": "shared"},
    )
    del up
    r = submit(client, app_token, doc(pid), "shared")
    assert r.status_code == 201


def test_the_run_list_says_whether_a_run_came_from_a_pipeline_or_an_upload(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    sent = submit(client, app_token, doc(pid, ref="refs/heads/main"), "pipeline-origin")
    assert sent.status_code == 201
    assert sent.json()["origin"] == "ci" and sent.json()["ref"] == "refs/heads/main"
    items = client.get(f"{APP}/scans").json()["items"]
    assert [(i["origin"], i["ref"]) for i in items] == [("ci", "refs/heads/main")]
    # A run that did not arrive through the CI endpoint has no "ci:" key, so it is an upload, and no ref.
    with engine(client).begin() as conn:
        conn.execute(update(AppScanRow).values(idempotency_key="browser-key", token_id=None, ref=None))
    after = client.get(f"{APP}/scans").json()["items"]
    assert [(i["origin"], i["ref"]) for i in after] == [("upload", None)]


def test_a_ci_run_stays_a_ci_run_after_its_token_is_deleted(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    run = submit(client, app_token, doc(pid), "pipeline-keep").json()["id"]
    with engine(client).begin() as conn:
        conn.execute(update(AppScanRow).values(token_id=None))
    listed = client.get(f"{APP}/scans").json()["items"]
    assert [(i["id"], i["origin"]) for i in listed] == [(run, "ci")]


# --- 13: limits that hold across instances -------------------------------------------------------------------


def test_the_per_token_hourly_limit_holds_across_two_instances(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    limit = {"app_ci_submissions_per_token_per_hour": 2}
    with make_app(make_settings, mailer, **limit) as a, make_app(make_settings, mailer, **limit) as b:
        signup(a, "owner@example.com", "Org")
        pid = new_project(a)
        token = make_token(a, "app").json()["token"]
        assert a.app.state.s is not b.app.state.s  # type: ignore[attr-defined]
        assert submit(a, token, doc(pid), "1").status_code == 201
        assert submit(b, token, doc(pid), "2").status_code == 201
        assert submit(a, token, doc(pid), "3").status_code == 429
        assert submit(b, token, doc(pid), "4").status_code == 429
        # a replay of an accepted run is not a new submission and is not limited
        assert submit(b, token, doc(pid), "1").status_code in (200, 201)
        assert len(rows(a, AppScanRow)) == 2


def test_the_monthly_plan_limit_still_applies_to_ci_runs(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    from dataclasses import replace

    from app.billing.plans import INTERNAL

    small = replace(INTERNAL, app_scans_per_month=2)

    async def plan(_org: str):  # type: ignore[no-untyped-def]
        return small

    client.app.state.s.entitlements.plan_for_async = plan
    assert submit(client, token, doc(pid), "m1").status_code == 201
    assert submit(client, token, doc(pid), "m2").status_code == 201
    assert submit(client, token, doc(pid), "m3").status_code == 403
    assert len(rows(client, AppScanRow)) == 2


# --- 14: incomplete and failed are never clean ---------------------------------------------------------------


def test_a_skipped_check_makes_the_run_incomplete_not_clean(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    body = doc(pid, findings=[])
    body["checks"][1] = {
        "kind": "secrets",
        "status": "skipped",
        "reason": "scanner not installed",
        "tool": {"name": "gitleaks", "version": "8.0"},
    }
    r = submit(client, app_token, body)
    assert r.status_code == 201
    out = r.json()
    assert out["status"] == "incomplete" and out["findings"] == []
    assert "clean" not in json.dumps(out).lower().replace("not clean", "")
    assert out["scanners"] and all(sc.get("reported_by") == "submitter" for sc in out["scanners"])


def test_findings_from_a_check_that_did_not_run_are_dropped(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    body = doc(pid)
    body["checks"] = [{"kind": "secrets", "status": "ran", "tool": {"name": "gitleaks", "version": "8"}}]
    out = submit(client, app_token, body).json()
    assert out["findings"] == []


def test_a_processing_defect_ends_failed_and_is_not_counted(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, _w = env
    import app.api.v1.app_scans as module

    def boom(_s: Any) -> Any:
        raise RuntimeError("internal detail with " + make_canary())

    monkeypatch.setattr(module, "build_outcome", boom)
    out = submit(client, app_token, doc(pid)).json()
    assert out["status"] == "failed" and "internal detail" not in json.dumps(out)
    assert usage(client) == 0


# --- 15: secrets and tokens do not leak -------------------------------------------------------------------


def test_token_values_and_submitted_secret_findings_do_not_leak(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, web = env
    canary = make_canary()
    body = doc(pid)
    body["findings"] = [
        {
            "kind": "secrets",
            "rule_id": "generic-api-key",
            "severity": "high",
            "confidence": "high",
            "path": "config/app.env",
            "line": 3,
            "title": "Key",
            "message": "A key was found",
        }
    ]
    handler, lines = capture_logs()
    logging.getLogger().addHandler(handler)
    try:
        r = submit(client, app_token, body)
        client.get(f"{API}/api-tokens")
        submit(client, "ssk_" + "z" * 40, body, "bad")
    finally:
        logging.getLogger().removeHandler(handler)
    assert r.status_code == 201
    dump = dump_tables(client, "app_scans", "app_findings", "audit_events")
    for secret in (app_token, web, "z" * 40):
        assert secret not in r.text and secret not in dump and all(secret not in ln for ln in lines)
    assert_no_canary(canary, r.text, dump, lines)
    assert "ssk_" not in dump and "ssa_" not in dump


def test_refusals_are_the_same_for_every_kind_of_bad_token(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, app_token, web = env
    bodies = {
        submit(client, t, doc(pid), "q").json()["detail"]
        for t in (web, "ssk_" + "0" * 40, "ssa_" + "0" * 40, "garbage")
    }
    assert len(bodies) == 1
    assert app_token not in "".join(bodies)


# --- provisional pilot settings ---------------------------------------------------------------------------


def test_pilot_defaults_and_the_lifetime_setting_is_honoured(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    defaults = make_settings()
    assert defaults.app_ci_token_days == 90 and defaults.app_ci_submissions_per_token_per_hour == 30
    with make_app(make_settings, mailer, app_ci_token_days=7) as client:
        signup(client, "o@example.com", "Org")
        created = make_token(client, "app").json()
        expires = datetime.fromisoformat(created["expires_at"])
        assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) < timedelta(days=7, hours=1)
        web = make_token(client, "web").json()
        assert web["expires_at"] is None  # Web Scanning tokens are unchanged


# --- findings of the independent review ---------------------------------------------------------------------


def test_web_tokens_keep_their_prefix_and_app_tokens_have_their_own(env) -> None:  # type: ignore[no-untyped-def]
    _client, _pid, app_token, web = env
    assert web.startswith("ssk_") and app_token.startswith("ssa_")


def test_parsing_a_submission_runs_off_the_event_loop(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    seen: list[bool] = []
    real = parse_submission

    def watch(document: Any) -> Any:
        try:
            asyncio.get_running_loop()
            seen.append(True)  # would block the loop
        except RuntimeError:
            seen.append(False)
        return real(document)

    monkeypatch.setattr(module, "parse_submission", watch)
    assert submit(client, token, doc(pid), "loop").status_code == 201
    assert seen == [False]


def test_browser_uploads_cannot_use_the_ci_key_namespace(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    lock = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {"": {"name": "x"}, "node_modules/lodash": {"version": "4.17.20"}},
        }
    )
    upload = {
        "project_id": pid,
        "kinds": ["dependency"],
        "files": [{"name": "package-lock.json", "content": lock}],
    }
    fine = client.post(f"{APP}/scans", json=upload, headers={"Idempotency-Key": "plain"})
    assert fine.status_code == 201  # the same upload is accepted with an ordinary key
    r = client.post(f"{APP}/scans", json=upload, headers={"Idempotency-Key": "ci:shared"})
    assert r.status_code == 422 and "not allowed" in r.json()["detail"]
    first = submit(client, token, doc(pid), "shared")
    assert first.status_code == 201 and "ci:shared" in [r.idempotency_key for r in rows(client, AppScanRow)]


def test_a_slow_body_is_cut_off() -> None:
    import asyncio

    from fastapi import HTTPException

    import app.api.v1.app_scans as module

    class Slow:
        headers: dict[str, str] = {}

        async def stream(self) -> Any:
            yield b"{"
            await asyncio.sleep(5)
            yield b"}"

    async def run() -> int:
        module.BODY_READ_SECONDS = 0.2
        try:
            await module._read_body(Slow(), 1024)  # type: ignore[arg-type]
        except HTTPException as exc:
            return exc.status_code
        finally:
            module.BODY_READ_SECONDS = 30
        return 0

    assert asyncio.run(run()) == 408


def test_an_unexpected_failure_after_acceptance_ends_the_run_failed_and_uncounted(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env

    def broken(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("storage down")

    monkeypatch.setattr(client.app.state.s.app_scans, "store_result", broken)
    with pytest.raises(RuntimeError):
        submit(client, token, doc(pid), "boom")
    monkeypatch.undo()
    statuses = [r.status for r in rows(client, AppScanRow)]
    assert statuses == ["failed"] and usage(client) == 0


# --- final pre-commit review: resource protection, revocation in flight, token slots ----------------------


def legal_findings(n: int) -> dict[str, Any]:
    body = doc("p")
    body["findings"] = [
        {
            "kind": "sast",
            "rule_id": f"r.{i}",
            "severity": "low",
            "confidence": "low",
            "path": f"src/f{i}.py",
            "line": i + 1,
            "title": "t",
            "message": "m" * 40,
        }
        for i in range(n)
    ]
    return body


def test_a_document_with_too_many_values_is_refused_before_the_secret_scan(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.appscan.submission as submission

    called: list[bool] = []
    monkeypatch.setattr(submission, "reject_if_secret", lambda _d: called.append(True))
    with pytest.raises(submission.SubmissionRejected) as err:
        submission.parse_submission({"x": ["a"] * (submission.MAX_NODES + 1)})
    assert err.value.code == "too_large" and called == []


def test_the_largest_legal_submission_is_still_accepted() -> None:
    import app.appscan.submission as submission
    from app.appscan.pipeline import MAX_FINDINGS

    nodes_per_finding = 17
    assert nodes_per_finding * MAX_FINDINGS < submission.MAX_NODES
    parsed = submission.parse_submission(legal_findings(5000))
    assert len(parsed.findings) == 5000


def _fake_state() -> Any:
    import asyncio

    class S:
        app_scan_semaphore = asyncio.Semaphore(1)

    return S()


def test_the_processing_slot_is_only_freed_when_the_thread_has_really_finished() -> None:
    import asyncio
    import threading

    import app.api.v1.app_scans as module

    release = threading.Event()
    started = threading.Event()

    def heavy() -> str:
        started.set()
        release.wait(5)
        return "done"

    async def run() -> tuple[bool, bool, bool]:
        state = _fake_state()
        first = asyncio.ensure_future(module._run_exclusive(state, heavy))
        await asyncio.to_thread(started.wait, 5)
        first.cancel()  # the request is cancelled while its thread is still working
        with pytest.raises(asyncio.CancelledError):
            await first
        held_after_cancel = state.app_scan_semaphore.locked()
        release.set()
        await asyncio.sleep(0.2)
        return held_after_cancel, state.app_scan_semaphore.locked(), True

    held, held_after_finish, _ = asyncio.run(run())
    assert held is True and held_after_finish is False


def test_a_request_waits_a_bounded_time_for_the_processing_slot() -> None:
    import asyncio
    import threading

    from fastapi import HTTPException

    import app.api.v1.app_scans as module

    release = threading.Event()

    async def run() -> int:
        state = _fake_state()
        module.CHECK_WAIT_SECONDS = 0.2
        try:
            busy = asyncio.ensure_future(module._run_exclusive(state, lambda: release.wait(5)))
            await asyncio.sleep(0.05)
            try:
                await module._run_exclusive(state, lambda: 1)
            except HTTPException as exc:
                return exc.status_code
            finally:
                release.set()
                await busy
        finally:
            module.CHECK_WAIT_SECONDS = 10
        return 0

    assert asyncio.run(run()) == 503


def test_a_check_that_takes_too_long_is_refused_and_stores_nothing(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import time

    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    monkeypatch.setattr(module, "CHECK_RUN_SECONDS", 0.2)
    monkeypatch.setattr(module, "_parse_document", lambda _raw: time.sleep(0.6))
    r = submit(client, token, doc(pid), "slow")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_complex"
    assert rows(client, AppScanRow) == []


def test_the_event_loop_keeps_running_while_a_heavy_document_is_checked() -> None:
    import asyncio
    import json as jsonlib

    import app.api.v1.app_scans as module

    raw = jsonlib.dumps({"x": ["a" * 19_990] * 150}).encode()  # CPU heavy, and refused as invalid

    async def run() -> float:
        state = _fake_state()
        worst = 0.0
        busy = asyncio.ensure_future(module._run_exclusive(state, module._parse_document, raw))
        last = asyncio.get_running_loop().time()
        while not busy.done():
            await asyncio.sleep(0.005)
            now = asyncio.get_running_loop().time()
            worst = max(worst, now - last - 0.005)
            last = now
        with pytest.raises(SubmissionRejected):
            busy.result()
        return worst

    assert asyncio.run(run()) < 0.25  # measured at about 0.015 s; the margin is for slow machines


def revoke_all_app_tokens(client: TestClient) -> None:
    from datetime import UTC, datetime

    with engine(client).begin() as conn:
        conn.execute(
            update(ApiTokenRow).where(ApiTokenRow.scope == "app").values(revoked_at=datetime.now(UTC))
        )


def test_a_token_revoked_while_its_request_is_in_flight_is_not_honoured(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    real = module._parse_document

    def revoke_then_parse(raw: bytes) -> Any:
        revoke_all_app_tokens(client)  # the owner revokes after authentication, before the run is accepted
        return real(raw)

    monkeypatch.setattr(module, "_parse_document", revoke_then_parse)
    r = submit(client, token, doc(pid), "inflight")
    assert r.status_code == 401
    assert rows(client, AppScanRow) == [] and usage(client) == 0


def test_a_token_that_expires_while_its_request_is_in_flight_is_not_honoured(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    real = module._parse_document

    def expire_then_parse(raw: bytes) -> Any:
        with engine(client).begin() as conn:
            conn.execute(
                update(ApiTokenRow)
                .where(ApiTokenRow.scope == "app")
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        return real(raw)

    monkeypatch.setattr(module, "_parse_document", expire_then_parse)
    assert submit(client, token, doc(pid), "inflight2").status_code == 401
    assert rows(client, AppScanRow) == []


def test_a_retry_after_revocation_is_refused_not_replayed(env) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    first = submit(client, token, doc(pid), "same")
    assert first.status_code == 201
    revoke_all_app_tokens(client)
    again = submit(client, token, doc(pid), "same")
    assert again.status_code == 401 and "replayed" not in again.text
    assert len(rows(client, AppScanRow)) == 1


def test_app_tokens_never_use_up_the_slots_of_web_integrations(env) -> None:  # type: ignore[no-untyped-def]
    from app.repositories.integrations import MAX_TOKENS_PER_ORGANIZATION as LIMIT

    client, *_ = env  # one web and one app token exist already
    for i in range(LIMIT - 1):
        assert make_token(client, "app").status_code == 201, i
    too_many = make_token(client, "app")
    assert too_many.status_code == 409 and "App Scanning API tokens" in too_many.json()["detail"]
    # Web Scanning still has all of its slots but the one it already uses.
    for i in range(LIMIT - 1):
        assert make_token(client, "web").status_code == 201, i
    web_full = make_token(client, "web")
    assert web_full.status_code == 409 and "App Scanning" not in web_full.json()["detail"]
    items = client.get(f"{API}/api-tokens").json()["items"]
    assert (
        sum(t["scope"] == "app" for t in items) == LIMIT and sum(t["scope"] == "web" for t in items) == LIMIT
    )


# --- last verification: cancellation, busy answers, shutdown, races, token slots -------------------------


def submit_headers(token: str, key: str) -> dict[str, str]:
    return {**bearer(token), "Idempotency-Key": key, "Content-Type": "application/json"}


def run_on_a_second_instance(make_settings: Any, mailer: Any, scenario: Any) -> Any:
    """Runs `scenario(app, client)` against a fresh application instance on the same database, with its own event
    loop, so a request task can be cancelled the way a server cancels it."""
    import asyncio

    import httpx

    async def main() -> Any:
        app = create_app(make_settings(app_scanning_enabled=True), mailer_for_second_instance)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
                return await scenario(app, http)

    mailer_for_second_instance = mailer
    return asyncio.run(main())


def test_a_cancelled_request_keeps_the_slot_until_its_thread_ends_and_leaves_no_run(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    import asyncio
    import threading

    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    started, release = threading.Event(), threading.Event()
    real = module._check_document

    def slow(raw: bytes) -> Any:
        started.set()
        release.wait(10)
        return real(raw)

    monkeypatch.setattr(module, "_check_document", slow)

    async def scenario(app: Any, http: Any) -> tuple[bool, bool]:
        state = app.state.s
        request = asyncio.ensure_future(
            http.post(SUBMIT, content=json.dumps(doc(pid)), headers=submit_headers(token, "cancel-1"))
        )
        await asyncio.to_thread(started.wait, 5)
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        held_while_thread_runs = state.app_scan_semaphore.locked()
        release.set()
        await asyncio.sleep(0.3)
        return held_while_thread_runs, state.app_scan_semaphore.locked()

    held, held_after = run_on_a_second_instance(make_settings, mailer, scenario)
    assert held is True and held_after is False
    assert rows(client, AppScanRow) == [] and usage(client) == 0


def test_a_request_cancelled_after_acceptance_ends_interrupted_and_uncounted(  # type: ignore[no-untyped-def]
    env, make_settings, mailer
) -> None:
    import asyncio
    import threading

    client, pid, token, _w = env
    started, release = threading.Event(), threading.Event()

    async def scenario(app: Any, http: Any) -> bool:
        state = app.state.s
        real = state.app_scans.store_result

        def slow_store(*args: Any) -> Any:
            started.set()
            release.wait(10)
            return real(*args)  # the run is final by then, so this must change nothing

        state.app_scans.store_result = slow_store
        request = asyncio.ensure_future(
            http.post(SUBMIT, content=json.dumps(doc(pid)), headers=submit_headers(token, "cancel-2"))
        )
        await asyncio.to_thread(started.wait, 5)
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)

        def status() -> str:
            with state.engine.connect() as conn:
                return str(conn.execute(select(AppScanRow.status)).scalar_one())

        # The handler ends the run in the background while the storing thread is still blocked. Wait until that
        # has happened before letting the thread go, so the order is fixed (either order leaves a consistent run).
        for _ in range(100):
            if await asyncio.to_thread(status) == "interrupted":
                break
            await asyncio.sleep(0.05)
        release.set()
        await asyncio.sleep(0.3)
        return bool(state.app_scan_semaphore.locked())

    assert run_on_a_second_instance(make_settings, mailer, scenario) is False
    scans = rows(client, AppScanRow)
    assert [s.status for s in scans] == ["interrupted"]
    assert rows(client, AppFindingRow) == [] and usage(client) == 0


def test_shutdown_with_a_check_in_flight_finishes_once_the_thread_does(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    import asyncio
    import threading
    import time

    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    started, release = threading.Event(), threading.Event()
    real = module._check_document

    def slow(raw: bytes) -> Any:
        started.set()
        release.wait(10)
        return real(raw)

    monkeypatch.setattr(module, "_check_document", slow)

    async def scenario(app: Any, http: Any) -> None:
        request = asyncio.ensure_future(
            http.post(SUBMIT, content=json.dumps(doc(pid)), headers=submit_headers(token, "shutdown"))
        )
        await asyncio.to_thread(started.wait, 5)
        request.cancel()  # what a server does to requests still running at shutdown
        await asyncio.gather(request, return_exceptions=True)
        threading.Timer(
            1.0, release.set
        ).start()  # the thread ends a second later, after the lifespan has ended

    begun = time.perf_counter()
    run_on_a_second_instance(make_settings, mailer, scenario)
    assert time.perf_counter() - begun < 8  # no hang: waiting for the thread is bounded by the thread
    assert rows(client, AppScanRow) == [] and usage(client) == 0


def test_a_busy_instance_answers_503_with_retry_after_and_recovers(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    started, release = threading.Event(), threading.Event()
    real = module._check_document

    def slow(raw: bytes) -> Any:
        started.set()
        release.wait(10)
        return real(raw)

    monkeypatch.setattr(module, "_check_document", slow)
    monkeypatch.setattr(module, "CHECK_WAIT_SECONDS", 0.3)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(submit, client, token, doc(pid), "busy-1")
        assert started.wait(5)
        second = submit(client, token, doc(pid), "busy-2")
        assert second.status_code == 503 and second.headers["retry-after"] == "30"
        assert rows(client, AppScanRow) == []  # nothing stored for the refused request
        release.set()
        assert first.result(timeout=10).status_code == 201
    monkeypatch.undo()
    assert submit(client, token, doc(pid), "busy-3").status_code == 201  # the slot is free again
    assert usage(client) == 2


def test_an_unexpected_worker_error_is_a_fixed_500_without_text_and_frees_the_slot(env, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.api.v1.app_scans as module

    client, pid, token, _w = env
    canary = make_canary()

    def broken(_raw: bytes) -> Any:
        raise RuntimeError(f"unexpected {canary}")

    handler, lines = capture_logs()
    logging.getLogger().addHandler(handler)
    real = module._parse_document
    monkeypatch.setattr(module, "_parse_document", broken)
    try:
        r = submit(client, token, doc(pid), "worker-error")
    finally:
        logging.getLogger().removeHandler(handler)
    assert r.status_code == 500 and r.json() == {"detail": "The submission could not be checked."}
    assert_no_canary(canary, r.text, lines)
    assert rows(client, AppScanRow) == [] and usage(client) == 0
    monkeypatch.setattr(module, "_parse_document", real)
    assert submit(client, token, doc(pid), "after-error").status_code == 201  # the slot was not left occupied


def _postgres_only(client: TestClient) -> None:
    if engine(client).dialect.name != "postgresql":
        pytest.skip("needs PostgreSQL row locks")


def test_a_revocation_that_commits_while_a_run_waits_for_the_workspace_lock_is_honoured(env) -> None:  # type: ignore[no-untyped-def]
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from time import sleep

    from sqlalchemy.orm import Session

    from app.repositories.appscans import TokenNoLongerValid
    from app.repositories.plans import lock_organization

    client, pid, _token, _w = env
    _postgres_only(client)
    state = client.app.state.s
    org = org_of(client)
    me = client.get(f"{API}/auth/me").json()["id"]
    token_id = next(t["id"] for t in client.get(f"{API}/api-tokens").json()["items"] if t["scope"] == "app")

    def accept() -> Any:
        return state.app_scans.accept_run(
            org,
            pid,
            me,
            ["sast"],
            [{"name": "ci-submission", "size": 1, "sha256": "0" * 64}],
            None,
            datetime.now(UTC),
            6,
            "ci:race",
            None,
            token_id,
            30,
        )

    with ThreadPoolExecutor(1) as pool, Session(engine(client)) as session, session.begin():
        lock_organization(session, org)  # another request is inside its own transaction for this workspace
        waiting = pool.submit(accept)
        sleep(0.6)
        assert not waiting.done()  # the run is waiting for the lock
        assert state.integrations.revoke_token(org, token_id)  # commits while it waits
    with pytest.raises(TokenNoLongerValid):
        waiting.result(timeout=10)
    assert rows(client, AppScanRow) == []


def test_concurrent_token_creation_cannot_exceed_the_limit_per_scope(env) -> None:  # type: ignore[no-untyped-def]
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.repositories.integrations import MAX_TOKENS_PER_ORGANIZATION as LIMIT

    client, *_ = env
    _postgres_only(client)
    state = client.app.state.s
    org = org_of(client)
    me = client.get(f"{API}/auth/me").json()["id"]
    barrier = Barrier(12)

    def create(i: int) -> bool:
        barrier.wait()
        scope = "web" if i % 2 == 0 else "app"
        return state.integrations.create_token(org, me, f"race-{i}", scope, timedelta(days=1)) is not None

    with ThreadPoolExecutor(12) as pool:
        made = list(pool.map(create, range(12)))
    items = client.get(f"{API}/api-tokens").json()["items"]
    assert (
        sum(t["scope"] == "web" for t in items) == LIMIT and sum(t["scope"] == "app" for t in items) == LIMIT
    )
    assert sum(made) == 2 * (LIMIT - 1)  # each scope already had one token


def test_revoking_a_token_frees_a_slot_in_its_own_scope_only(env) -> None:  # type: ignore[no-untyped-def]
    from app.repositories.integrations import MAX_TOKENS_PER_ORGANIZATION as LIMIT

    client, *_ = env
    for _ in range(LIMIT - 1):
        assert make_token(client, "app").status_code == 201
        assert make_token(client, "web").status_code == 201
    assert make_token(client, "app").status_code == 409 and make_token(client, "web").status_code == 409
    items = client.get(f"{API}/api-tokens").json()["items"]
    app_id = next(t["id"] for t in items if t["scope"] == "app")
    client.delete(f"{API}/api-tokens/{app_id}").raise_for_status()
    assert make_token(client, "web").status_code == 409  # an App slot does not help Web
    assert make_token(client, "app").status_code == 201
    web_id = next(t["id"] for t in client.get(f"{API}/api-tokens").json()["items"] if t["scope"] == "web")
    client.delete(f"{API}/api-tokens/{web_id}").raise_for_status()
    assert make_token(client, "app").status_code == 409  # a Web slot does not help App
    assert make_token(client, "web").status_code == 201
