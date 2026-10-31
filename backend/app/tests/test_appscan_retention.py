"""App Scanning history follows the workspace's plan, like website scans: runs and their findings are deleted
once older than the plan's history period (30, 90 or 365 days). The clean-up never changes what a workspace has
used this month, never touches a run that is still queued or running, and keeps projects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.appscan.pipeline import DependencyFinding, ScanOutcome
from app.appscan.states import AppScanStatus
from app.billing.plans import current_period
from app.core.config import Settings
from app.main import create_app
from app.models.app_scan import AppFindingRow, AppProjectRow, AppScanRow
from app.repositories.appscans import AppScanRepository
from app.schemas.scan import Confidence, Severity
from app.tests.conftest import signup

API = "/api/v1"
# A fixed "now" late in a 31-day month, so a 30-day history and the current usage month differ.
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
PERIOD_START, _ = current_period(NOW)


def state_of(client: TestClient) -> Any:
    return client.app.state.s  # type: ignore[attr-defined]


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


@pytest.fixture
def app(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings: Settings = make_settings(
        default_plan=None
    )  # unassigned workspaces are on Free, as in production
    with TestClient(create_app(settings, mailer)) as client:
        yield client


@pytest.fixture
def repo(app: TestClient) -> AppScanRepository:
    return AppScanRepository(state_of(app).engine)


def workspace(app: TestClient, email: str, plan: str | None = None) -> str:
    signup(app, email, f"{email} org")
    org = org_of(app)
    if plan:
        state_of(app).plans.set_plan(org, plan, "system")
    return org


FINDING = DependencyFinding(
    rule_id="GHSA-aaaa-bbbb-cccc",
    title="lodash 4.17.20 has a known vulnerability (GHSA-aaaa-bbbb-cccc)",
    severity=Severity.HIGH,
    confidence=Confidence.HIGH,
    description="d",
    remediation="r",
    ecosystem="npm",
    package_name="lodash",
    package_version="4.17.20",
    path="package-lock.json",
    fixed_versions=("4.17.21",),
    references=(),
    aliases=(),
    fingerprint="f" * 64,
)


def run(repo: AppScanRepository, org: str, project: str, created: datetime, *, finish: bool = True) -> str:
    """A run created at `created`, finished with one finding unless `finish` is False (then it stays queued)."""
    accepted = repo.accept_run(
        org,
        project,
        None,
        kinds=["dependency"],
        inputs=[{"name": "package-lock.json", "size": 10, "sha256": "a" * 64}],
        monthly_limit=None,
        period_start=PERIOD_START,
        per_project_hourly_limit=None,
    )
    if finish:
        assert repo.start_run(org, accepted.scan_id)
        outcome = ScanOutcome(
            status=AppScanStatus.COMPLETED, findings=[FINDING], checks_run=["dependency"], packages_checked=1
        )
        assert repo.store_result(org, accepted.scan_id, outcome)
    with repo._session.begin() as session:  # noqa: SLF001  (tests set the age directly)
        session.execute(
            update(AppScanRow).where(AppScanRow.id == accepted.scan_id).values(created_at=created)
        )
    return accepted.scan_id


def ids(repo: AppScanRepository) -> set[str]:
    with repo._session() as session:  # noqa: SLF001
        return set(session.scalars(select(AppScanRow.id)))


def findings_of(repo: AppScanRepository, scan_id: str) -> int:
    with repo._session() as session:  # noqa: SLF001
        return int(
            session.scalar(
                select(func.count()).select_from(AppFindingRow).where(AppFindingRow.scan_id == scan_id)
            )
            or 0
        )


def test_free_keeps_30_days_and_deletes_older_runs_with_their_findings(
    app: TestClient, repo: AppScanRepository
) -> None:
    org = workspace(app, "free@example.com")
    project = repo.create_project(org, None, "web", "upload", project_limit=None)
    old = run(repo, org, project, NOW - timedelta(days=45))
    recent = run(repo, org, project, NOW - timedelta(days=10))
    assert findings_of(repo, old) == 1

    assert repo.delete_expired_history(NOW) == 1
    assert ids(repo) == {recent}
    assert findings_of(repo, old) == 0, "findings go with their run"
    assert findings_of(repo, recent) == 1


def test_runs_from_the_current_usage_month_are_never_deleted(
    app: TestClient, repo: AppScanRepository
) -> None:
    """31 October: a run from 1 October is past Free's 30 days but was counted in October's allowance."""
    org = workspace(app, "month@example.com")
    project = repo.create_project(org, None, "web", "upload", project_limit=None)
    early_this_month = run(repo, org, project, PERIOD_START + timedelta(minutes=1))
    last_month = run(repo, org, project, PERIOD_START - timedelta(minutes=1))
    used_before = repo.usage(org, PERIOD_START).runs

    repo.delete_expired_history(NOW)
    assert ids(repo) == {early_this_month}
    assert repo.usage(org, PERIOD_START).runs == used_before, (
        "deleting history never hands back a counted run"
    )
    assert last_month not in ids(repo)


@pytest.mark.parametrize(
    ("plan", "kept_days", "deleted_days"), [("professional", 80, 100), ("agency", 300, 400)]
)
def test_paid_plans_keep_their_longer_history(
    app: TestClient, repo: AppScanRepository, plan: str, kept_days: int, deleted_days: int
) -> None:
    org = workspace(app, f"{plan}@example.com", plan)
    project = repo.create_project(org, None, "web", "upload", project_limit=None)
    kept = run(repo, org, project, NOW - timedelta(days=kept_days))
    run(repo, org, project, NOW - timedelta(days=deleted_days))

    assert repo.delete_expired_history(NOW) == 1
    assert ids(repo) == {kept}


def test_each_workspace_follows_its_own_plan(app: TestClient, repo: AppScanRepository) -> None:
    free = workspace(app, "a@example.com")
    pro = workspace(app, "b@example.com", "professional")
    free_project = repo.create_project(free, None, "web", "upload", project_limit=None)
    pro_project = repo.create_project(pro, None, "web", "upload", project_limit=None)
    free_old = run(repo, free, free_project, NOW - timedelta(days=60))
    pro_same_age = run(repo, pro, pro_project, NOW - timedelta(days=60))

    repo.delete_expired_history(NOW)
    assert free_old not in ids(repo)
    assert pro_same_age in ids(repo)


def test_queued_or_running_runs_and_projects_are_kept(app: TestClient, repo: AppScanRepository) -> None:
    org = workspace(app, "active@example.com")
    project = repo.create_project(org, None, "web", "upload", project_limit=None)
    stuck = run(repo, org, project, NOW - timedelta(days=200), finish=False)

    assert repo.delete_expired_history(NOW) == 0
    assert stuck in ids(repo)
    with repo._session() as session:  # noqa: SLF001
        assert session.scalar(select(func.count()).select_from(AppProjectRow)) == 1


def test_website_scans_are_not_touched(app: TestClient, repo: AppScanRepository) -> None:
    org = workspace(app, "web@example.com")
    project = repo.create_project(org, None, "web", "upload", project_limit=None)
    run(repo, org, project, NOW - timedelta(days=60))
    web_before = state_of(app).repo.delete_expired_history()  # the website clean-up still runs on its own
    assert repo.delete_expired_history(NOW) == 1
    assert web_before == 0
