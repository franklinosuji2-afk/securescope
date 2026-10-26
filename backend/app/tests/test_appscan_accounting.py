"""App Scanning run accounting, plan isolation and workspace isolation (decisions D1, D2, D4, D5, D6).

These test the repository and the plan catalogue. There are no App Scanning routes yet, so nothing here proves
route-level enforcement; that is tested when the routes exist."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, update

from alembic import command
from app.appscan.states import AppScanStatus
from app.billing.errors import PlanLimitError
from app.billing.plans import AGENCY, FREE, INTERNAL, PLANS, PROFESSIONAL, current_period, get_plan
from app.core.config import Settings
from app.database.migrate import alembic_config
from app.main import create_app
from app.models.app_scan import AppProjectRow, AppScanRow
from app.repositories.appscans import (
    AcceptedRun,
    AppProjectNameTaken,
    AppProjectNotFound,
    AppRateLimited,
    AppScanRepository,
    IdempotencyKeyReused,
)
from app.tests.canary import assert_no_canary, make_canary
from app.tests.conftest import signup

API = "/api/v1"

PERIOD_START, _ = current_period(datetime.now(UTC))


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def state_of(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.s  # type: ignore[attr-defined]


@pytest.fixture
def free_app(make_settings, mailer):  # type: ignore[no-untyped-def]
    """The real default: workspaces without an assigned plan are on Free."""
    settings: Settings = make_settings(default_plan=None)
    with TestClient(create_app(settings, mailer)) as client:
        yield client


@pytest.fixture
def alice(free_app: TestClient) -> TestClient:
    signup(free_app, "alice@example.com", "Alice Org")
    return free_app


INPUT = [{"name": "package-lock.json", "size": 120, "sha256": "a" * 64}]


@pytest.fixture
def repo(alice: TestClient) -> AppScanRepository:
    return AppScanRepository(state_of(alice).engine)


@pytest.fixture
def org(alice: TestClient) -> str:
    return org_of(alice)


@pytest.fixture
def project(repo: AppScanRepository, org: str) -> str:
    return repo.create_project(org, None, "shop-api", "upload", project_limit=None)


def accept(repo: AppScanRepository, org: str, project: str, **kw: Any) -> AcceptedRun:
    args: dict[str, Any] = {
        "kinds": ["dependency"],
        "inputs": INPUT,
        "monthly_limit": 100,
        "period_start": PERIOD_START,
        "per_project_hourly_limit": None,
    }
    args.update(kw)
    return repo.accept_run(org, project, None, **args)


# --- plan catalogue (D2, D3, D4) ----------------------------------------------------------------------


def test_web_scanning_limits_are_unchanged() -> None:
    assert (FREE.scans_per_month, PROFESSIONAL.scans_per_month, AGENCY.scans_per_month) == (3, 30, 150)
    assert (FREE.max_websites, PROFESSIONAL.max_websites, AGENCY.max_websites) == (1, 5, 20)
    assert (FREE.history_days, PROFESSIONAL.history_days, AGENCY.history_days) == (30, 90, 365)
    assert (FREE.scheduled_scans, PROFESSIONAL.scheduled_scans, AGENCY.scheduled_scans) == (False, True, True)
    assert (FREE.price_eur_month, PROFESSIONAL.price_eur_month, AGENCY.price_eur_month) == (0, 19, 49)
    assert (FREE.purchasable, PROFESSIONAL.purchasable, AGENCY.purchasable) == (False, True, True)


def test_free_has_browser_upload_but_no_app_scanning_ci_tokens() -> None:
    assert FREE.app_ci_tokens is False
    assert PROFESSIONAL.app_ci_tokens and AGENCY.app_ci_tokens and INTERNAL.app_ci_tokens


def test_provisional_allowances_are_kept_separate_from_web_allowances() -> None:
    assert (FREE.app_scans_per_month, PROFESSIONAL.app_scans_per_month, AGENCY.app_scans_per_month) == (
        5,
        100,
        500,
    )
    assert INTERNAL.app_scans_per_month is None and INTERNAL.app_projects is None
    for plan in PLANS.values():
        assert plan.app_scans_per_month != plan.scans_per_month or plan is INTERNAL


def test_unknown_plan_gets_the_most_restrictive_app_scanning_rights() -> None:
    plan = get_plan("no-such-plan")
    assert plan is FREE and plan.app_ci_tokens is False


def test_app_scanning_is_off_by_default_and_not_shown_in_the_plan_api(alice: TestClient, org: str) -> None:
    assert state_of(alice).settings.app_scanning_enabled is False
    body = alice.get(f"{API}/organizations/{org}/plan").text
    assert "app_" not in body


# --- run accounting (D1) ------------------------------------------------------------------------------


def test_an_accepted_run_is_counted_and_has_its_own_counter(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    web_before = state_of(alice).plans.usage(org, PERIOD_START)
    accept(repo, org, project)
    accept(repo, org, project)
    assert repo.usage(org, PERIOD_START).runs == 2
    assert state_of(alice).plans.usage(org, PERIOD_START) == web_before  # website usage did not move


def test_website_scans_do_not_use_up_app_scanning_runs(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    user = alice.get(f"{API}/auth/me").json()["id"]
    for _ in range(3):
        state_of(alice).repo.create_scan(
            org, user, "https://a.example.com/", "a.example.com", None, 3, PERIOD_START
        )
    assert repo.usage(org, PERIOD_START).runs == 0
    accept(repo, org, project, monthly_limit=1)  # the web pool is exhausted; the app pool is untouched


def test_the_monthly_limit_is_enforced_by_the_server(repo: AppScanRepository, org: str, project: str) -> None:
    accept(repo, org, project, monthly_limit=2)
    accept(repo, org, project, monthly_limit=2)
    with pytest.raises(PlanLimitError, match="App Scanning runs per month"):
        accept(repo, org, project, monthly_limit=2)
    assert repo.usage(org, PERIOD_START).runs == 2


def test_a_plan_without_the_feature_accepts_nothing(repo: AppScanRepository, org: str, project: str) -> None:
    with pytest.raises(PlanLimitError):
        accept(repo, org, project, monthly_limit=0)


def test_rejected_requests_are_not_counted(
    repo: AppScanRepository, org: str, project: str, alice: TestClient
) -> None:
    bad: list[dict[str, Any]] = [
        {"kinds": []},
        {"kinds": ["not-a-check"]},
        {"inputs": [INPUT[0]] * 6},
        {"idempotency_key": "has space"},
        {"idempotency_key": "k" * 81},
        {"inputs": [{"name": "x" * 20_000}]},
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            accept(repo, org, project, **kwargs)
    with pytest.raises(AppProjectNotFound):
        accept(repo, org, "0" * 32)
    assert repo.usage(org, PERIOD_START).runs == 0
    with state_of(alice).engine.connect() as conn:
        assert conn.execute(select(AppScanRow.id)).all() == []


def test_findings_do_not_make_a_run_unsuccessful_so_completed_and_incomplete_runs_count(
    repo: AppScanRepository, org: str, project: str
) -> None:
    for status in (AppScanStatus.COMPLETED, AppScanStatus.INCOMPLETE, AppScanStatus.CANCELLED):
        run = accept(repo, org, project).scan_id
        repo.start_run(org, run)
        assert repo.finish_run(org, run, status)
    assert repo.usage(org, PERIOD_START).runs == 3


@pytest.mark.parametrize("status", [AppScanStatus.FAILED, AppScanStatus.INTERRUPTED])
def test_infrastructure_and_scanner_failures_do_not_consume_a_run(
    repo: AppScanRepository, org: str, project: str, status: AppScanStatus
) -> None:
    run = accept(repo, org, project, monthly_limit=1).scan_id
    repo.start_run(org, run)
    repo.finish_run(org, run, status, error="The scanner stopped.")
    assert repo.usage(org, PERIOD_START).runs == 0
    accept(repo, org, project, monthly_limit=1)  # the single allowed run is still available


def test_a_restart_marks_unfinished_runs_interrupted_and_not_counted(
    repo: AppScanRepository, org: str, project: str
) -> None:
    queued = accept(repo, org, project).scan_id
    running = accept(repo, org, project).scan_id
    repo.start_run(org, running)
    done = accept(repo, org, project).scan_id
    repo.start_run(org, done)
    repo.finish_run(org, done, AppScanStatus.COMPLETED)
    assert repo.interrupt_unfinished() == 2
    assert {repo.get_run(org, r).status for r in (queued, running)} == {"interrupted"}  # type: ignore[union-attr]
    assert repo.get_run(org, done).status == "completed"  # type: ignore[union-attr]
    assert repo.usage(org, PERIOD_START).runs == 1
    assert "restarted" in (repo.get_run(org, queued).error or "")  # type: ignore[union-attr]


def test_a_finished_run_cannot_be_changed_again(repo: AppScanRepository, org: str, project: str) -> None:
    run = accept(repo, org, project).scan_id
    repo.start_run(org, run)
    assert repo.finish_run(
        org, run, AppScanStatus.INCOMPLETE, checks_skipped=[{"check": "dependency", "reason": "unavailable"}]
    )
    assert not repo.finish_run(org, run, AppScanStatus.COMPLETED)
    assert not repo.start_run(org, run)
    row = repo.get_run(org, run)
    assert row is not None and row.status == "incomplete" and "unavailable" in (row.checks_skipped_json or "")
    with pytest.raises(ValueError):
        repo.finish_run(org, run, AppScanStatus.RUNNING)


def test_runs_from_an_earlier_month_are_not_counted(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    run = accept(repo, org, project).scan_id
    with state_of(alice).engine.begin() as conn:
        conn.execute(
            update(AppScanRow).where(AppScanRow.id == run).values(created_at=PERIOD_START - timedelta(days=1))
        )
    assert repo.usage(org, PERIOD_START).runs == 0


# --- duplicate retries ---------------------------------------------------------------------------------


def test_a_retry_with_the_same_key_returns_the_first_run_and_is_not_charged_again(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    first = accept(repo, org, project, idempotency_key="ci-run-42", monthly_limit=1)
    again = accept(repo, org, project, idempotency_key="ci-run-42", monthly_limit=1)
    assert not first.replay and again.replay and again.scan_id == first.scan_id
    assert repo.usage(org, PERIOD_START).runs == 1
    with state_of(alice).engine.connect() as conn:
        assert len(conn.execute(select(AppScanRow.id)).all()) == 1


def test_a_retry_is_returned_even_when_the_allowance_is_now_used_up(
    repo: AppScanRepository, org: str, project: str
) -> None:
    first = accept(repo, org, project, idempotency_key="k1", monthly_limit=1)
    assert accept(repo, org, project, idempotency_key="k1", monthly_limit=1).scan_id == first.scan_id


def test_a_key_cannot_be_reused_for_another_project(repo: AppScanRepository, org: str, project: str) -> None:
    other = repo.create_project(org, None, "other", "upload", None)
    accept(repo, org, project, idempotency_key="shared")
    with pytest.raises(IdempotencyKeyReused):
        accept(repo, org, other, idempotency_key="shared")


def test_the_same_key_in_two_workspaces_makes_two_runs(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    with TestClient(alice.app) as bob:
        signup(bob, "bob@example.com", "Bob Org")
        bob_org = org_of(bob)
        bob_project = repo.create_project(bob_org, None, "shop-api", "upload", None)
        a = accept(repo, org, project, idempotency_key="same")
        b = accept(repo, bob_org, bob_project, idempotency_key="same")
    assert a.scan_id != b.scan_id and not a.replay and not b.replay


def _skip_unless_postgres(repo_engine) -> None:  # type: ignore[no-untyped-def]
    if repo_engine.dialect.name != "postgresql":
        pytest.skip(
            "Needs PostgreSQL row locks; the same limitation applies to the existing plan concurrency tests."
        )


def test_simultaneous_requests_cannot_exceed_the_allowance(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    _skip_unless_postgres(state_of(alice).engine)
    results: list[str] = []

    def attempt() -> None:
        try:
            accept(repo, org, project, monthly_limit=3)
            results.append("created")
        except PlanLimitError:
            results.append("refused")

    threads = [threading.Thread(target=attempt) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("created") == 3 and results.count("refused") == 9


def test_simultaneous_retries_with_one_key_make_one_run(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    _skip_unless_postgres(state_of(alice).engine)
    ids: list[str] = []
    threads = [
        threading.Thread(
            target=lambda: ids.append(
                accept(repo, org, project, idempotency_key="race", monthly_limit=1).scan_id
            )
        )
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(ids)) == 1 and repo.usage(org, PERIOD_START).runs == 1


# --- per-project hourly limit (D6) ---------------------------------------------------------------------


def test_the_hourly_limit_applies_per_project(repo: AppScanRepository, org: str, project: str) -> None:
    other = repo.create_project(org, None, "other", "upload", None)
    accept(repo, org, project, per_project_hourly_limit=2)
    accept(repo, org, project, per_project_hourly_limit=2)
    with pytest.raises(AppRateLimited, match="hourly limit"):
        accept(repo, org, project, per_project_hourly_limit=2)
    accept(repo, org, other, per_project_hourly_limit=2)  # another project is not affected


def test_older_runs_leave_the_hourly_window_and_failed_runs_still_count_towards_it(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    old = accept(repo, org, project).scan_id
    failed = accept(repo, org, project).scan_id
    repo.start_run(org, failed)
    repo.finish_run(org, failed, AppScanStatus.FAILED)
    with state_of(alice).engine.begin() as conn:
        conn.execute(
            update(AppScanRow)
            .where(AppScanRow.id == old)
            .values(created_at=datetime.now(UTC) - timedelta(hours=2))
        )
    with pytest.raises(AppRateLimited):
        accept(repo, org, project, per_project_hourly_limit=1)  # the failed run is within the hour
    accept(repo, org, project, per_project_hourly_limit=2)


# --- projects (D5) -------------------------------------------------------------------------------------


def test_the_project_cap_is_enforced_and_archiving_frees_a_slot(repo: AppScanRepository, org: str) -> None:
    first = repo.create_project(org, None, "one", "upload", project_limit=1)
    with pytest.raises(PlanLimitError, match="projects"):
        repo.create_project(org, None, "two", "upload", project_limit=1)
    assert repo.archive_project(org, first)
    repo.create_project(org, None, "two", "upload", project_limit=1)
    assert repo.usage(org, PERIOD_START).projects == 1


def test_project_names_are_unique_per_workspace_and_validated(
    alice: TestClient, repo: AppScanRepository, org: str
) -> None:
    repo.create_project(org, None, "Shop", "upload", None)
    with pytest.raises(AppProjectNameTaken):
        repo.create_project(org, None, "Shop", "upload", None)
    for bad in ("", "   ", "x" * 121, "bad\x00name", "line\nbreak"):
        if bad.strip() and "\n" in bad:
            continue  # whitespace is normalised, so an embedded newline becomes a space
        with pytest.raises(ValueError):
            repo.create_project(org, None, bad, "upload", None)
    with pytest.raises(ValueError):
        repo.create_project(org, None, "ok", "elsewhere", None)
    with TestClient(alice.app) as bob:
        signup(bob, "bob@example.com", "Bob Org")
        repo.create_project(org_of(bob), None, "Shop", "upload", None)  # the same name elsewhere is fine


def test_an_archived_project_accepts_no_runs(repo: AppScanRepository, org: str, project: str) -> None:
    repo.archive_project(org, project)
    with pytest.raises(AppProjectNotFound):
        accept(repo, org, project)


# --- workspace isolation -------------------------------------------------------------------------------


def test_another_workspace_cannot_see_or_change_a_project_or_run(
    alice: TestClient, repo: AppScanRepository, org: str, project: str
) -> None:
    run = accept(repo, org, project).scan_id
    bob = TestClient(
        alice.app
    )  # no `with`: entering the lifespan again would (correctly) interrupt the queued run
    signup(bob, "bob@example.com", "Bob Org")
    bob_org = org_of(bob)
    assert repo.list_projects(bob_org) == []
    with pytest.raises(AppProjectNotFound):
        accept(repo, bob_org, project)
    assert repo.get_run(bob_org, run) is None
    assert not repo.start_run(bob_org, run)
    assert not repo.finish_run(bob_org, run, AppScanStatus.COMPLETED)
    assert not repo.archive_project(bob_org, project)
    assert repo.find_by_idempotency_key(bob_org, "anything") is None
    assert repo.usage(bob_org, PERIOD_START).runs == 0
    assert repo.get_run(org, run).status == "queued"  # type: ignore[union-attr]


# --- nothing sensitive is stored -----------------------------------------------------------------------


def test_secrets_are_redacted_before_anything_is_stored(
    alice: TestClient, repo: AppScanRepository, org: str
) -> None:
    canary = make_canary()
    project = repo.create_project(org, None, f"proj {canary}", "ci", None)
    run = accept(
        repo,
        org,
        project,
        inputs=[{"name": f"{canary}.txt", "size": 1, "sha256": "b" * 64}],
        ref=f"branch-{canary}",
    ).scan_id
    repo.start_run(org, run)
    repo.finish_run(
        org, run, AppScanStatus.FAILED, error=f"token {canary} rejected",
        checks_skipped=[{"check": canary, "reason": "x"}], scanners=[{"name": canary, "version": "1"}],
    )  # fmt: skip
    with state_of(alice).engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(select(AppScanRow)).all()]
        rows += [tuple(r) for r in conn.execute(select(AppProjectRow)).all()]
    assert_no_canary(canary, rows)


# --- migration -----------------------------------------------------------------------------------------


def test_the_migration_adds_only_new_tables_and_can_be_stepped_back(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = alembic_config(url)
    command.upgrade(config, "0020")
    engine = create_engine(url)
    before = {
        t: {c["name"] for c in inspect(engine).get_columns(t)} for t in inspect(engine).get_table_names()
    }
    assert "app_scans" not in before
    command.upgrade(config, "0021")
    after = {
        t: {c["name"] for c in inspect(engine).get_columns(t)} for t in inspect(engine).get_table_names()
    }
    assert set(after) - set(before) == {"app_projects", "app_scans"}
    assert all(after[t] == before[t] for t in before if t != "alembic_version")  # no existing table changed
    command.downgrade(config, "0020")
    assert set(inspect(engine).get_table_names()) == set(before)
    command.upgrade(config, "head")
    engine.dispose()
