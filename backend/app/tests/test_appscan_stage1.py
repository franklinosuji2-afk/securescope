"""Stage 1 (dormant deployment): App Scanning must be off by default, unreachable while off, silent, and additive.

These are the checks the Stage 1 runbook points to. They prove what the code does in this repository; they say
nothing about a production database, which nobody here has touched."""

from __future__ import annotations

import ast
import re
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.billing.plans import FREE
from app.core.config import Settings
from app.database.migrate import alembic_config
from app.main import create_app
from app.tests.conftest import signup
from app.tests.test_integrations import bearer, make_token
from app.tests.test_tenancy import org_of

API = "/api/v1"
BACKEND = Path(__file__).resolve().parents[2]
APP_TABLES = ("app_projects", "app_scans", "app_findings")


def operations(client: TestClient) -> list[tuple[str, str]]:
    found = []
    for path, methods in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        for method in methods:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"} and path.startswith(f"{API}/app/"):
                found.append((method.upper(), path))
    return found


def app_rows(client: TestClient) -> int:
    engine = client.app.state.s.engine  # type: ignore[attr-defined]
    with engine.connect() as conn:
        return sum(int(conn.execute(text(f"select count(*) from {t}")).scalar_one()) for t in APP_TABLES)


# --- the flag ------------------------------------------------------------------------------------------


def test_the_flag_is_off_by_default_and_not_set_by_any_deployment_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SECURESCOPE_APP_SCANNING_ENABLED", raising=False)
    assert Settings().app_scanning_enabled is False
    root = BACKEND.parent
    for name in ("render.yaml", "docker-compose.yml", "frontend/wrangler.jsonc", "backend/Dockerfile"):
        path = root / name
        if path.exists():
            assert "APP_SCANNING" not in path.read_text(encoding="utf-8").upper(), name
    for value, expected in (("false", False), ("0", False), ("true", True)):
        monkeypatch.setenv("SECURESCOPE_APP_SCANNING_ENABLED", value)
        assert Settings().app_scanning_enabled is expected


def test_while_off_every_route_is_404_for_everyone_and_writes_nothing(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as owner:  # default settings: flag off
        signup(owner, "owner@example.com", "Org")
        token = make_token(owner)["token"]
        ops = operations(owner)
        assert len(ops) >= 7, "the App Scanning routes were not found"
        scan_body = {
            "project_id": "0" * 32,
            "kinds": ["dependency"],
            "files": [{"name": "requirements.txt", "content": "flask==3.0.0\n"}],
        }
        callers = {
            "signed-in owner": owner,
            "anonymous": TestClient(owner.app),
            "bearer token": None,
        }
        wrong: list[str] = []
        for method, path in ops:
            url = re.sub(r"\{[^}]+\}", "0" * 32, path)
            body = scan_body if path.endswith("/scans") and method == "POST" else {"name": "x"}
            for who, client in callers.items():
                if client is None:
                    response = TestClient(owner.app).request(method, url, json=body, headers=bearer(token))
                else:
                    response = client.request(method, url, json=body)
                if response.status_code != 404:
                    wrong.append(f"{who} {method} {url} -> {response.status_code}")
        assert wrong == []
        assert app_rows(owner) == 0


def test_the_answer_while_off_does_not_depend_on_headers_or_query_tricks(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(), mailer)) as owner:
        signup(owner, "owner@example.com", "Org")
        org = org_of(owner)
        tricks: list[dict[str, str]] = [
            {"X-Organization-Id": org},
            {"X-App-Scanning": "1"},
            {"X-Forwarded-For": "127.0.0.1"},
            {"X-HTTP-Method-Override": "GET"},
            {"Origin": "http://localhost"},
        ]
        for headers in tricks:
            # A refusal by an earlier control (the origin check) is as good as a 404; a 2xx would be the bug.
            got = owner.get(f"{API}/app/overview?enabled=true&app_scanning_enabled=1", headers=headers)
            made = owner.post(f"{API}/app/projects", json={"name": "x"}, headers=headers)
            assert got.status_code in (403, 404) and made.status_code in (403, 404)
            if "Origin" not in headers:
                assert got.status_code == 404 and made.status_code == 404
        # Path variants must not reach the handlers either.
        for path in (
            "/app/overview/",
            "/APP/overview",
            "/app//overview",
            "/app/overview%2f",
            "/app/./overview",
        ):
            assert owner.get(f"{API}{path}").status_code in (404, 307, 308, 405), path
        assert app_rows(owner) == 0


def test_the_flag_is_read_from_the_server_settings_only(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    off = TestClient(create_app(make_settings(), mailer))
    on = TestClient(create_app(make_settings(app_scanning_enabled=True), mailer))
    with off, on:
        signup(on, "owner@example.com", "Org")
        assert on.get(f"{API}/app/overview").status_code == 200
        signup(off, "second@example.com", "Org Two")
        assert off.get(f"{API}/app/overview").status_code == 404


# --- nothing leaves, nothing is sent -----------------------------------------------------------------------


def test_no_network_connection_is_opened_by_anything_in_app_scanning_even_when_switched_on(
    make_settings: Any, mailer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections: list[Any] = []
    original = socket.socket.connect

    def spy(self: socket.socket, address: Any) -> Any:
        if self.family != socket.AF_UNIX:
            connections.append(address)
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", spy)
    with TestClient(
        create_app(make_settings(app_scanning_enabled=True, default_plan=None), mailer)
    ) as client:
        signup(client, "owner@example.com", "Org")
        project = client.post(f"{API}/app/projects", json={"name": "web"}).json()["id"]
        sent_before = len(mailer.sent)
        body = {
            "project_id": project,
            "kinds": ["dependency"],
            "files": [{"name": "requirements.txt", "content": "flask==3.0.0\n"}],
        }
        response = client.post(f"{API}/app/scans", json=body)
        assert response.status_code == 201
        # The default source is "unavailable": nothing is looked up, so the run fails and is not counted.
        assert response.json()["result"] == "scanner_error"
        assert len(mailer.sent) == sent_before, "App Scanning must not send email"
    outside = [c for c in connections if str(c[0]) not in ("127.0.0.1", "::1", "localhost", "testserver")]
    assert outside == []


def test_app_scanning_code_imports_no_http_client_mailer_webhook_or_billing_module() -> None:
    forbidden = {
        "httpx",
        "requests",
        "urllib",
        "urllib3",
        "http",
        "aiohttp",
        "socket",
        "smtplib",
        "ssl",
        "subprocess",
        "asyncio.subprocess",
        "app.mailer",
        "app.billing.lifecycle",
        "app.billing.preview",
    }
    files = list((BACKEND / "app" / "appscan").glob("*.py"))
    files += [BACKEND / "app/api/v1/app_scans.py", BACKEND / "app/repositories/appscans.py"]
    offenders: list[str] = []
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name in forbidden or any(name.startswith(f + ".") for f in forbidden):
                    offenders.append(f"{path.name}: {name}")
    assert offenders == []
    lowered = " ".join(p.read_text(encoding="utf-8").lower() for p in files)
    for word in ("osv.dev", "api.osv", "paddle", "webhook", "send_mail", "notify"):
        assert word not in lowered, word


def test_the_default_vulnerability_source_cannot_answer(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from app.appscan.vulns import SourceUnavailable

    with TestClient(create_app(make_settings(), mailer)) as client:
        source = client.app.state.s.app_source  # type: ignore[attr-defined]
        with pytest.raises(SourceUnavailable):
            source.lookup([])


# --- tokens and entitlements ---------------------------------------------------------------------------------


def test_a_free_workspace_cannot_get_any_api_token_and_a_paid_token_does_not_open_app_scanning(
    make_settings: Any, mailer: Any
) -> None:
    assert FREE.app_ci_tokens is False
    with TestClient(create_app(make_settings(default_plan=None, app_scanning_enabled=True), mailer)) as free:
        signup(free, "free@example.com", "Free Org")
        assert free.post(f"{API}/api-tokens", json={"name": "ci"}).status_code == 403
        assert free.get(f"{API}/app/overview").json()["ci_tokens_available"] is False
    with TestClient(
        create_app(make_settings(default_plan="professional", app_scanning_enabled=True), mailer)
    ) as pro:
        signup(pro, "pro@example.com", "Pro Org")
        token = make_token(pro)["token"]
        runner = TestClient(pro.app)
        for method, path in operations(pro):
            url = re.sub(r"\{[^}]+\}", "0" * 32, path)
            response = runner.request(method, url, json={}, headers=bearer(token))
            assert response.status_code in (401, 403), f"{method} {url} -> {response.status_code}"


def test_existing_plan_entitlements_are_unchanged() -> None:
    """The values the previous release shipped, copied from commit 08e46d3 (the last deployed state)."""
    from app.billing.plans import AGENCY, INTERNAL, PROFESSIONAL

    def shipped(plan: Any) -> tuple[Any, ...]:
        return (
            plan.price_eur_month,
            plan.max_websites,
            plan.scans_per_month,
            plan.history_days,
            plan.can_invite,
            plan.purchasable,
            plan.client_workspace,
            plan.scheduled_scans,
        )

    assert shipped(FREE) == (0, 1, 3, 30, False, False, False, False)
    assert shipped(PROFESSIONAL) == (19, 5, 30, 90, False, True, False, True)
    assert shipped(AGENCY) == (49, 20, 150, 365, True, True, True, True)
    assert shipped(INTERNAL) == (0, None, None, 365, True, False, True, True)


# --- migrations -------------------------------------------------------------------------------------------


def snapshot(engine: Any, only: set[str] | None = None) -> dict[str, Any]:
    insp = inspect(engine)
    out: dict[str, Any] = {}
    for table in insp.get_table_names():
        if table == "alembic_version" or (only is not None and table not in only):
            continue
        out[table] = {
            "columns": [(c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(table)],
            "indexes": sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(table)
            ),
            "fks": sorted(
                (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
                for f in insp.get_foreign_keys(table)
            ),
            "unique": sorted(tuple(u["column_names"]) for u in insp.get_unique_constraints(table)),
        }
    return out


def test_migrations_0021_and_0022_only_add_tables_and_change_nothing_that_exists(db_url: str) -> None:
    engine = create_engine(db_url)
    config = alembic_config(db_url)
    command.downgrade(config, "0020")
    before = snapshot(engine)
    assert not set(APP_TABLES) & set(before)
    with engine.begin() as conn:  # a row that must survive the upgrade untouched
        conn.execute(
            text(
                "insert into organizations (id, name, slug, status, created_at, updated_at) values ('o1', 'Keep', 'keep', 'active', '2026-10-01', '2026-10-01')"
            )
        )
    command.upgrade(config, "0022")
    after = snapshot(engine)
    assert set(after) - set(before) == set(APP_TABLES)
    assert {t: after[t] for t in before} == before, "an existing table changed"
    with engine.connect() as conn:
        assert conn.execute(text("select name from organizations where id='o1'")).scalar_one() == "Keep"
    # Rolling back (scratch databases only) removes exactly the new tables and restores the old schema.
    command.downgrade(config, "0020")
    assert snapshot(engine) == before
    command.upgrade(config, "head")
    engine.dispose()


def test_migration_0023_adds_scope_and_expiry_without_broadening_any_existing_token(db_url: str) -> None:
    engine = create_engine(db_url)
    config = alembic_config(db_url)
    command.downgrade(config, "0022")
    before = snapshot(engine)
    stamp = "'2026-10-01'"
    with engine.begin() as conn:  # a token as the previous release writes it
        conn.execute(
            text(
                "insert into organizations (id, name, slug, status, created_at, updated_at) "
                f"values ('o1', 'Keep', 'keep', 'active', {stamp}, {stamp})"
            )
        )
        conn.execute(
            text(
                "insert into users (id, email, password_hash, account_status, created_at, updated_at) "
                f"values ('u1', 'a@example.com', 'x', 'ACTIVE', {stamp}, {stamp})"
            )
        )
        conn.execute(
            text(
                "insert into api_tokens (id, organization_id, created_by, name, token_hash, prefix, created_at) "
                f"values ('t1', 'o1', 'u1', 'legacy', '{'a' * 64}', 'ssk_aaaa', {stamp})"
            )
        )
    command.upgrade(config, "0023")
    after = snapshot(engine)
    changed = {t for t in before if after[t] != before[t]}
    assert changed == {"api_tokens", "app_scans"}, changed
    assert [c[0] for c in after["api_tokens"]["columns"] if c not in before["api_tokens"]["columns"]] == [
        "scope",
        "expires_at",
    ]
    assert [c[0] for c in after["app_scans"]["columns"] if c not in before["app_scans"]["columns"]] == [
        "token_id"
    ]
    with engine.connect() as conn:
        scope, expires = conn.execute(text("select scope, expires_at from api_tokens where id='t1'")).one()
    assert scope == "web" and expires is None  # unchanged behaviour, and no App Scanning access
    # Rolling back removes App Scanning tokens (never turns them into Web tokens) and restores the schema.
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into api_tokens (id, organization_id, created_by, name, token_hash, prefix, created_at, scope) "
                f"values ('t2', 'o1', 'u1', 'ci', '{'b' * 64}', 'ssk_bbbb', {stamp}, 'app')"
            )
        )
    command.downgrade(config, "0022")
    assert snapshot(engine) == before
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("select id from api_tokens order by id"))] == ["t1"]
    command.upgrade(config, "head")
    engine.dispose()


def test_the_migration_files_contain_no_data_statements_jobs_or_destructive_operations() -> None:
    for name in ("0021_app_scanning_tables.py", "0022_app_findings.py"):  # 0023 alters tables on purpose
        source = (BACKEND / "alembic" / "versions" / name).read_text(encoding="utf-8")
        upgrade = source.split("def downgrade", 1)[0]
        for forbidden in (
            "op.execute",
            "bulk_insert",
            "drop_table",
            "drop_column",
            "alter_column",
            "add_column",
            "rename",
            "DROP",
            "DELETE",
            "UPDATE",
        ):
            assert forbidden not in upgrade, f"{name}: {forbidden} in upgrade()"
        assert upgrade.count("create_table") >= 1


def test_deleting_an_account_still_works_when_app_scanning_rows_exist(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(app_scanning_enabled=True), mailer)) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = type(  # type: ignore[attr-defined]
            "S",
            (),
            {
                "max_batch": 10,
                "lookup": lambda self, p: __import__("app.appscan.vulns", fromlist=["x"]).LookupResult(
                    [[] for _ in p]
                ),
            },
        )()
        pid = client.post(f"{API}/app/projects", json={"name": "web"}).json()["id"]
        body = {
            "project_id": pid,
            "kinds": ["dependency"],
            "files": [{"name": "requirements.txt", "content": "flask==3.0.0\n"}],
        }
        assert client.post(f"{API}/app/scans", json=body).status_code == 201
        assert app_rows(client) >= 2
        response = client.request(
            "DELETE", f"{API}/account", json={"password": "correct-horse-battery-staple", "confirm": "DELETE"}
        )
        assert response.status_code == 204, response.text
        assert app_rows(client) == 0
