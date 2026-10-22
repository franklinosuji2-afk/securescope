"""Scan comparison and CSV export."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.reporting.compare import compare_scans
from app.reporting.csv_export import HEADER, safe_cell, to_csv
from app.schemas.scan import Finding, ScanDetail, ScanStatus, Severity
from app.tests.conftest import signup
from app.tests.test_tenancy import API, finished_scan

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def finding(fid: str, severity: Severity = Severity.LOW, **extra: object) -> Finding:
    return Finding(
        id=fid,
        title=f"Title {fid}",
        severity=severity,
        category="headers",
        description="d",
        remediation="r",
        fingerprint=f"fp-{fid}",
        **extra,
    )


def scan(sid: str, minutes: int, findings: list[Finding], score: int = 90, host: str = "a.example") -> ScanDetail:
    return ScanDetail(
        id=sid,
        target_url=f"https://{host}",
        host=host,
        status=ScanStatus.COMPLETED,
        score=score,
        grade="B",
        created_at=T0 + timedelta(minutes=minutes),
        findings=findings,
    )


# --- comparison ---------------------------------------------------------------------------------------


def test_new_resolved_and_unchanged_come_only_from_the_stored_findings() -> None:
    old = scan("s1", 0, [finding("A"), finding("B", Severity.HIGH)], score=70)
    new = scan("s2", 10, [finding("B", Severity.HIGH), finding("C", Severity.MEDIUM)], score=80)
    result = compare_scans(old, new)
    assert [f.id for f in result.new_findings] == ["C"]
    assert [f.id for f in result.resolved_findings] == ["A"]
    assert [f.id for f in result.unchanged_findings] == ["B"]
    assert result.score_change == 10


def test_the_order_of_the_two_arguments_does_not_matter() -> None:
    old = scan("s1", 0, [finding("A")], score=70)
    new = scan("s2", 10, [], score=100)
    assert compare_scans(old, new) == compare_scans(new, old)
    assert compare_scans(new, old).older.id == "s1"


def test_findings_are_listed_most_severe_first() -> None:
    old = scan("s1", 0, [])
    new = scan("s2", 5, [finding("L", Severity.LOW), finding("H", Severity.HIGH), finding("M", Severity.MEDIUM)])
    assert [f.id for f in compare_scans(old, new).new_findings] == ["H", "M", "L"]


def test_identical_scans_report_no_change() -> None:
    a = scan("s1", 0, [finding("A")])
    b = scan("s2", 5, [finding("A")])
    result = compare_scans(a, b)
    assert not result.new_findings
    assert not result.resolved_findings
    assert result.score_change == 0


def test_the_comparison_never_claims_a_fix() -> None:
    assert "not proof" in compare_scans(scan("s1", 0, []), scan("s2", 1, [])).note


# --- csv --------------------------------------------------------------------------------------------


def test_cells_that_could_run_as_formulas_are_neutralised() -> None:
    for bad in ("=1+1", "+SUM(A1)", "-2", "@cmd", "\tx", "\rx"):
        assert safe_cell(bad).startswith("'")
    assert safe_cell("plain") == "plain"
    assert safe_cell(None) == ""


def test_the_csv_has_one_row_per_finding_and_a_fixed_header() -> None:
    detail = scan("s1", 0, [finding("A"), finding("B", Severity.HIGH)])
    rows = list(csv.reader(io.StringIO(to_csv(detail))))
    assert tuple(rows[0]) == HEADER
    assert len(rows) == 3
    assert {r[3] for r in rows[1:]} == {"A", "B"}


def test_text_that_came_from_a_website_cannot_become_a_formula() -> None:
    nasty = Finding(
        id="SS-X-1",
        title='=HYPERLINK("http://evil.example","click")',
        severity=Severity.LOW,
        category="headers",
        description="+cmd|' /C calc'!A0",
        remediation="@SUM(1)",
    )
    rows = list(csv.reader(io.StringIO(to_csv(scan("s1", 0, [nasty])))))
    assert all(not cell.startswith(("=", "+", "@")) for cell in rows[1])
    assert rows[1][7].startswith("'=")


def test_a_comma_or_quote_inside_a_value_stays_in_one_cell() -> None:
    odd = finding("A")
    odd.description = 'has, a comma and "quotes"\nand a newline'
    rows = list(csv.reader(io.StringIO(to_csv(scan("s1", 0, [odd])))))
    assert len(rows[1]) == len(HEADER)
    assert rows[1][10] == odd.description


# --- api --------------------------------------------------------------------------------------------


def test_compare_and_csv_over_the_api(local_client: TestClient, mock_server: str) -> None:
    first = finished_scan(local_client, mock_server)
    second = finished_scan(local_client, mock_server)
    result = local_client.get(f"{API}/scans/{second}/compare", params={"with": first})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["older"]["id"] != body["newer"]["id"]
    assert {body["older"]["id"], body["newer"]["id"]} == {first, second}
    assert body["new_findings"] == []
    assert body["resolved_findings"] == []
    exported = local_client.get(f"{API}/scans/{first}/report", params={"format": "csv"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.headers["content-disposition"].endswith('.csv"')
    assert tuple(next(csv.reader(io.StringIO(exported.text)))) == HEADER


def test_a_scan_cannot_be_compared_with_itself_or_a_missing_scan(
    local_client: TestClient, mock_server: str
) -> None:
    sid = finished_scan(local_client, mock_server)
    assert local_client.get(f"{API}/scans/{sid}/compare", params={"with": sid}).status_code == 400
    assert local_client.get(f"{API}/scans/{sid}/compare", params={"with": "nope"}).status_code == 404
    assert local_client.get(f"{API}/scans/{sid}/compare").status_code == 422


def test_another_workspaces_scan_cannot_be_compared_or_exported(
    local_client: TestClient, mock_server: str
) -> None:
    mine = finished_scan(local_client, mock_server)
    other = TestClient(local_client.app)
    signup(other, "someone-else@example.com", "Other Org")
    assert other.get(f"{API}/scans/{mine}/compare", params={"with": mine}).status_code == 404
    assert other.get(f"{API}/scans/{mine}/report", params={"format": "csv"}).status_code == 404


def test_comparison_needs_a_signed_in_user(anon_client: TestClient) -> None:
    assert anon_client.get(f"{API}/scans/abc/compare", params={"with": "def"}).status_code == 401
