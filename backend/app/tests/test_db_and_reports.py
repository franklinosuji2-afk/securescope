from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, inspect, select, update

from app.database.migrate import upgrade
from app.database.session import make_engine
from app.models.scan import FindingRow, ScanRow
from app.reporting import reports
from app.repositories.accounts import AccountRepository
from app.repositories.scans import ScanRepository
from app.schemas.scan import Finding, ScanStatus, Severity, TargetMetadata


def sample_findings() -> list[Finding]:
    return [
        Finding(
            id="SS-T-1",
            title="<script>alert(1)</script>",
            severity=Severity.HIGH,
            category="c|d",
            description="desc *bold*",
            evidence='x"><img src=x onerror=alert(1)>',
            remediation="fix `it`",
        ),
        Finding(
            id="SS-T-2",
            title="low one",
            severity=Severity.LOW,
            category="c",
            description="d",
            remediation="r",
        ),
    ]


def make_meta() -> TargetMetadata:
    return TargetMetadata(requested_url="https://a.example/", host="a.example")


def make_repo(url: str) -> ScanRepository:
    return ScanRepository(make_engine(url))


def make_org(url: str, email: str = "t@example.com") -> tuple[str, str]:
    """(organization_id, user_id) for tests that talk to the repository directly."""
    accounts = AccountRepository(make_engine(url))
    user, membership = accounts.create_user_with_org(email, "x", "Test Org")
    return membership.organization_id, user.id


def test_migrations_are_idempotent_and_create_schema(db_url: str) -> None:
    upgrade(db_url)  # a second run on an up-to-date database must be a no-op
    tables = set(inspect(make_engine(db_url)).get_table_names())
    assert {
        "scans",
        "findings",
        "alembic_version",
        "users",
        "organizations",
        "organization_members",
        "sessions",
        "account_tokens",
        "audit_events",
    } <= tables


def test_scan_lifecycle_and_ordering(db_url: str) -> None:
    repo = make_repo(db_url)
    org, user = make_org(db_url)
    first = repo.create_scan(org, user, "https://a.example/", "a.example")
    second = repo.create_scan(org, user, "https://b.example/", "b.example")
    assert repo.get_scan(first, org).status is ScanStatus.QUEUED  # type: ignore[union-attr]
    repo.mark_running(first)
    repo.complete_scan(first, sample_findings(), 76, "C", make_meta())
    repo.fail_scan(second, "boom")
    done = repo.get_scan(first, org)
    assert done and done.status is ScanStatus.COMPLETED and done.score == 76
    assert [f.id for f in done.findings] == ["SS-T-1", "SS-T-2"]
    assert done.counts["high"] == 1 and done.counts["low"] == 1
    assert done.created_at.tzinfo is not None
    failed = repo.get_scan(second, org)
    assert failed and failed.error == "boom" and failed.findings == []
    items, total = repo.list_scans(org)
    assert total == 2 and [i.id for i in items] == [second, first]  # newest first
    assert repo.get_scan("nope", org) is None
    assert repo.ping() is True


def test_retention_and_interrupted(db_url: str) -> None:
    repo = make_repo(db_url)
    org, user = make_org(db_url)
    old = repo.create_scan(org, user, "https://old.example/", "old.example")
    repo.complete_scan(old, sample_findings(), 50, "D", make_meta())
    fresh = repo.create_scan(org, user, "https://new.example/", "new.example")
    stale = datetime.now(UTC) - timedelta(days=45)
    with repo.engine.begin() as conn:
        conn.execute(update(ScanRow).where(ScanRow.id == old).values(created_at=stale))
    assert repo.delete_older_than(30) == 1
    assert repo.get_scan(old, org) is None
    with repo.engine.connect() as conn:  # findings are removed with their scan
        assert conn.scalar(select(func.count()).select_from(FindingRow)) == 0
    assert repo.fail_interrupted() == 1
    assert repo.get_scan(fresh, org).status is ScanStatus.FAILED  # type: ignore[union-attr]


def completed_detail(db_url: str):  # type: ignore[no-untyped-def]
    repo = make_repo(db_url)
    org, user = make_org(db_url)
    scan_id = repo.create_scan(org, user, "https://a.example/?q=<b>", "a.example")
    repo.complete_scan(scan_id, sample_findings(), 76, "C", make_meta())
    detail = repo.get_scan(scan_id, org)
    assert detail is not None
    return detail


def test_html_report_escapes_untrusted_values(db_url: str) -> None:
    page = reports.to_html(completed_detail(db_url))
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page
    assert "not a penetration test" in page


def test_markdown_report_neutralizes_markup(db_url: str) -> None:
    text = reports.to_markdown(completed_detail(db_url))
    assert "\\<script\\>" in text
    assert "Heuristic score: 76/100" in text
    assert "not proof of security" in text


def test_filename_is_sanitized(db_url: str) -> None:
    detail = completed_detail(db_url).model_copy(update={"host": '../../etc/pass"wd'})
    name = reports.safe_filename(detail, "json")
    assert "/" not in name and '"' not in name and name.endswith(".json")


def test_reports_state_coverage_and_limits(db_url: str) -> None:
    detail = completed_detail(db_url)
    assert detail.metadata is not None
    detail = detail.model_copy(
        update={"metadata": detail.metadata.model_copy(update={"checks_run": ["https", "hsts", "csp"]})}
    )
    text = reports.to_markdown(detail)
    assert "## What was checked" in text and "## Limits of this scan" in text
    assert "This is not a full TLS test" in text
    assert "Passed: " in text
    page = reports.to_html(detail)
    assert "What was checked" in page and "Limits of this scan" in page
