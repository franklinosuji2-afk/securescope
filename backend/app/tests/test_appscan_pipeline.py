"""The dependency scan pipeline with fake vulnerability sources. No network client exists; these tests prove how
results, statuses and storage behave, in particular that missing answers are never read as "clean"."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.appscan import pipeline as p
from app.appscan.manifests import Package, ParseResult, Unsupported
from app.appscan.states import AppScanStatus
from app.appscan.vulns import Advisory, LookupResult, SourceInfo, SourceUnavailable
from app.billing.plans import current_period
from app.core.config import Settings
from app.main import create_app
from app.models.app_scan import AppFindingRow
from app.repositories.appscans import AppScanRepository
from app.schemas.scan import Severity
from app.tests.canary import assert_no_canary, make_canary
from app.tests.conftest import signup

API = "/api/v1"

PROJECT = "p" * 32
RepoOrg = tuple[AppScanRepository, str, str]


def org_of(client: TestClient) -> str:
    return client.get(f"{API}/auth/me").json()["organizations"][0]["id"]  # type: ignore[no-any-return]


def state_of(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.s  # type: ignore[attr-defined]


@pytest.fixture
def free_app(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings: Settings = make_settings(default_plan=None)
    with TestClient(create_app(settings, mailer)) as client:
        yield client


def pkg(name: str, version: str = "1.0.0", file: str = "package-lock.json") -> Package:
    return Package("npm", name, version, file)


def parsed(packages: list[Package], unsupported: int = 0) -> list[ParseResult]:
    result = ParseResult("package-lock.json", 10, "a" * 64, packages=packages)
    result.unsupported = [Unsupported("package-lock.json", "range")] * unsupported
    return [result]


class FakeSource:
    def __init__(
        self, table: Mapping[str, list[Advisory] | None] | None = None, max_batch: int = 1000
    ) -> None:
        self.table = table or {}
        self.max_batch = max_batch
        self.calls: list[list[str]] = []

    def lookup(self, packages: Sequence[Package]) -> LookupResult:
        self.calls.append([x.name for x in packages])
        return LookupResult(
            [self.table.get(x.name, []) for x in packages], SourceInfo("fake-db", "1", "2026-10-26")
        )


class DownSource:
    max_batch = 1000

    def lookup(self, packages: Sequence[Package]) -> LookupResult:
        raise SourceUnavailable


ADV = Advisory(
    "GHSA-aaaa-bbbb-cccc",
    "Prototype pollution",
    ("CVE-2021-23337",),
    "high",
    ("4.17.21",),
    ("https://github.com/advisories/GHSA-aaaa-bbbb-cccc",),
)


# --- statuses ------------------------------------------------------------------------------------------


def test_everything_checked_and_nothing_found_is_completed_with_the_checks_listed() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a"), pkg("b")]), FakeSource())
    assert out.status is AppScanStatus.COMPLETED and out.findings == []
    assert out.checks_run == ["dependency"] and out.checks_skipped == [] and out.packages_checked == 2
    assert out.scanners == [{"name": "fake-db", "version": "1", "data_timestamp": "2026-10-26"}]


def test_findings_do_not_make_the_scan_unsuccessful() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("lodash", "4.17.20")]), FakeSource({"lodash": [ADV]}))
    assert out.status is AppScanStatus.COMPLETED and len(out.findings) == 1
    f = out.findings[0]
    assert (
        f.severity is Severity.HIGH and f.fixed_versions == ("4.17.21",) and f.aliases == ("CVE-2021-23337",)
    )
    assert "Upgrade lodash" in f.remediation and "does not change your dependencies" in f.remediation


def test_an_unreachable_source_is_a_failed_scan_never_a_clean_one() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a")]), DownSource())
    assert out.status is AppScanStatus.FAILED and out.findings == [] and out.checks_run == []
    assert out.packages_not_answered == 1 and "could not be reached" in (out.error or "")


def test_a_crashing_source_degrades_the_scan_and_leaks_nothing() -> None:
    secret = make_canary()

    class Broken:
        max_batch = 10

        def lookup(self, packages: Sequence[Package]) -> LookupResult:
            raise RuntimeError(f"boom {secret}")

    out = p.run_dependency_scan(PROJECT, parsed([pkg("a")]), Broken())
    assert out.status is AppScanStatus.FAILED
    assert_no_canary(secret, repr(out))


def test_partial_answers_make_the_scan_incomplete_and_say_which_part() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a"), pkg("b")]), FakeSource({"b": None}))
    assert out.status is AppScanStatus.INCOMPLETE
    assert out.packages_checked == 1 and out.packages_not_answered == 1
    assert any("no answer for 1 packages" in s["reason"] for s in out.checks_skipped)


def test_one_failed_batch_does_not_hide_the_findings_from_the_others() -> None:
    class Flaky(FakeSource):
        def lookup(self, packages: Sequence[Package]) -> LookupResult:
            if packages[0].name == "a":
                raise SourceUnavailable
            return super().lookup(packages)

    src = Flaky({"c": [ADV]}, max_batch=1)
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a"), pkg("c")]), src)
    assert out.status is AppScanStatus.INCOMPLETE and len(out.findings) == 1


def test_unsupported_entries_make_the_scan_incomplete_even_when_everything_else_is_clean() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a")], unsupported=3), FakeSource())
    assert out.status is AppScanStatus.INCOMPLETE and out.findings == []
    assert any("3 entries could not be checked" in s["reason"] for s in out.checks_skipped)


def test_no_packages_is_a_failure_not_a_clean_result() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([], unsupported=2), FakeSource())
    assert out.status is AppScanStatus.FAILED and "No checkable packages" in (out.error or "")


def test_a_reply_that_does_not_line_up_is_not_trusted() -> None:
    class Short(FakeSource):
        def lookup(self, packages: Sequence[Package]) -> LookupResult:
            return LookupResult([[]], SourceInfo("x"))  # one answer for two packages

    out = p.run_dependency_scan(PROJECT, parsed([pkg("a"), pkg("b")]), Short())
    assert out.status is AppScanStatus.FAILED and out.packages_checked == 0


def test_the_time_budget_stops_further_lookups_and_marks_the_rest_unchecked() -> None:
    now = [0.0]

    def clock() -> float:
        now[0] += 10.0
        return now[0]

    out = p.run_dependency_scan(
        PROJECT,
        parsed([pkg("a"), pkg("b"), pkg("c")]),
        FakeSource(max_batch=1),
        budget_seconds=15.0,
        clock=clock,
    )
    assert out.status is AppScanStatus.INCOMPLETE and 0 < out.packages_checked < 3


def test_packages_are_sent_in_batches_and_duplicates_once() -> None:
    src = FakeSource(max_batch=2)
    p.run_dependency_scan(PROJECT, parsed([pkg("a"), pkg("b"), pkg("c"), pkg("a")]), src)
    assert src.calls == [["a", "b"], ["c"]]


def test_the_findings_cap_marks_the_scan_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(p, "MAX_FINDINGS", 2)
    table = {n: [ADV] for n in "abc"}
    out = p.run_dependency_scan(PROJECT, parsed([pkg(n) for n in "abc"]), FakeSource(table))
    assert out.status is AppScanStatus.INCOMPLETE and len(out.findings) == 2


# --- normalisation -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "severity", "given"),
    [
        ("CRITICAL", Severity.CRITICAL, True),
        ("High", Severity.HIGH, True),
        ("moderate", Severity.MEDIUM, True),
        ("low", Severity.LOW, True),
        ("9.8", Severity.CRITICAL, True),
        ("7.0", Severity.HIGH, True),
        ("5.3", Severity.MEDIUM, True),
        ("2.0", Severity.LOW, True),
        ("0", Severity.INFO, True),
        ("11", Severity.MEDIUM, False),
        ("nonsense", Severity.MEDIUM, False),
        ("", Severity.MEDIUM, False),
        (None, Severity.MEDIUM, False),
    ],
)
def test_severity_is_normalised_and_missing_severity_is_stated_not_invented(
    raw: str | None, severity: Severity, given: bool
) -> None:
    assert p.normalise_severity(raw) == (severity, given)


def test_a_missing_severity_is_said_in_the_finding() -> None:
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a")]), FakeSource({"a": [Advisory("CVE-2020-1")]}))
    f = out.findings[0]
    assert f.severity is Severity.MEDIUM and "did not give a severity" in f.description
    assert "no fixed version" in f.remediation


def test_findings_are_sorted_most_severe_first() -> None:
    table = {
        "low": [Advisory("A-1", severity="low")],
        "crit": [Advisory("A-2", severity="critical")],
        "mid": [Advisory("A-3", severity="medium")],
    }
    out = p.run_dependency_scan(PROJECT, parsed([pkg(n) for n in table]), FakeSource(table))
    assert [f.severity for f in out.findings] == [Severity.CRITICAL, Severity.MEDIUM, Severity.LOW]


def test_the_fingerprint_is_stable_across_versions_and_differs_by_project_and_advisory() -> None:
    a = p.fingerprint(PROJECT, "GHSA-1", "npm", "x")
    assert a == p.fingerprint(PROJECT, "GHSA-1", "npm", "x")
    assert (
        len({a, p.fingerprint("q" * 32, "GHSA-1", "npm", "x"), p.fingerprint(PROJECT, "GHSA-2", "npm", "x")})
        == 3
    )
    one = p.run_dependency_scan(PROJECT, parsed([pkg("x", "1.0.0")]), FakeSource({"x": [ADV]}))
    two = p.run_dependency_scan(PROJECT, parsed([pkg("x", "1.0.1")]), FakeSource({"x": [ADV]}))
    assert one.findings[0].fingerprint == two.findings[0].fingerprint


def test_untrusted_advisory_text_is_cleaned_before_use() -> None:
    secret = make_canary()
    hostile = Advisory(
        "GHSA-x\nINJECT",
        summary=f"<script>alert(1)</script>\x00\x1b[31m token {secret} " + "A" * 5000,
        references=(
            "javascript:alert(1)",
            "http://insecure.example/x",
            "https://ok.example/advisory",
            "https://" + "a" * 400,
        ),
        fixed_versions=("1.0.1", "bad version", "2.0.0\nx"),
        severity="high",
    )
    good = Advisory(
        "GHSA-good",
        summary=hostile.summary,
        references=hostile.references,
        fixed_versions=hostile.fixed_versions,
    )
    out = p.run_dependency_scan(PROJECT, parsed([pkg("a")]), FakeSource({"a": [hostile, good]}))
    assert [f.rule_id for f in out.findings] == [
        "GHSA-good"
    ]  # an advisory id with control characters is dropped
    f = out.findings[0]
    assert_no_canary(secret, f.description)
    assert "\x00" not in f.description and "\x1b" not in f.description and len(f.description) < 800
    assert f.references == ("https://ok.example/advisory",) and f.fixed_versions == ("1.0.1",)


# --- storage -------------------------------------------------------------------------------------------


@pytest.fixture
def repo_org(free_app: TestClient) -> RepoOrg:
    signup(free_app, "alice@example.com", "Alice Org")
    repo = AppScanRepository(state_of(free_app).engine)
    org = org_of(free_app)
    return repo, org, repo.create_project(org, None, "shop", "upload", None)


def test_findings_and_final_state_are_stored_together_and_read_back(
    repo_org: RepoOrg, free_app: TestClient
) -> None:
    repo, org, project = repo_org
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["dependency"], [], 100, start, None).scan_id
    repo.start_run(org, scan)
    out = p.run_dependency_scan(project, parsed([pkg("lodash", "4.17.20")]), FakeSource({"lodash": [ADV]}))
    assert repo.store_result(org, scan, out)
    row = repo.get_run(org, scan)
    assert row is not None and row.status == "completed" and "dependency" in (row.checks_run_json or "")
    stored = repo.get_findings(org, scan)
    assert (
        len(stored) == 1 and stored[0].rule_id == "GHSA-aaaa-bbbb-cccc" and stored[0].package_name == "lodash"
    )
    assert stored[0].evidence is None and stored[0].severity == "high"


def test_a_final_run_keeps_its_result_and_other_workspaces_see_nothing(
    repo_org: RepoOrg, free_app: TestClient
) -> None:
    repo, org, project = repo_org
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["dependency"], [], 100, start, None).scan_id
    first = p.run_dependency_scan(project, parsed([pkg("lodash")]), FakeSource({"lodash": [ADV]}))
    assert repo.store_result(org, scan, first)
    second = p.run_dependency_scan(project, parsed([pkg("a")]), FakeSource())
    assert not repo.store_result(org, scan, second)  # already final
    assert len(repo.get_findings(org, scan)) == 1
    with TestClient(free_app.app) as bob:
        signup(bob, "bob@example.com", "Bob Org")
        bob_org = org_of(bob)
    assert repo.get_findings(bob_org, scan) == []
    assert not repo.store_result(bob_org, scan, second)


def test_failed_scans_are_not_counted_and_cannot_be_finished_with_an_active_state(repo_org: RepoOrg) -> None:
    repo, org, project = repo_org
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["dependency"], [], 100, start, None).scan_id
    out = p.run_dependency_scan(project, parsed([pkg("a")]), DownSource())
    assert repo.store_result(org, scan, out)
    assert repo.get_run(org, scan).status == "failed"  # type: ignore[union-attr]
    assert repo.usage(org, start).runs == 0
    bad = p.ScanOutcome(status=AppScanStatus.RUNNING)
    with pytest.raises(ValueError):
        repo.store_result(org, scan, bad)


def test_no_secret_from_the_source_reaches_the_database(repo_org: RepoOrg, free_app: TestClient) -> None:
    repo, org, project = repo_org
    secret = make_canary()
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["dependency"], [], 100, start, None).scan_id
    adv = Advisory("GHSA-leak", summary=f"password = {secret}", severity="low")
    repo.store_result(org, scan, p.run_dependency_scan(project, parsed([pkg("a")]), FakeSource({"a": [adv]})))
    with state_of(free_app).engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(select(AppFindingRow)).all()]
    assert rows
    assert_no_canary(secret, rows)
