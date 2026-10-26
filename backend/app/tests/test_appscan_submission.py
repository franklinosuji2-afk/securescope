"""CI submissions (static analysis and secret detection results): strict schema, secret refusal without echo,
honest status, safe rendering and storage. No route exists yet; these test the module and the repository."""

from __future__ import annotations

import copy
import dataclasses
import json
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.appscan import submission as sm
from app.appscan.pipeline import CodeFinding
from app.appscan.states import AppScanStatus
from app.billing.plans import current_period
from app.core.config import Settings
from app.main import create_app
from app.models.app_scan import AppFindingRow
from app.repositories.appscans import AppScanRepository
from app.tests.canary import assert_no_canary, make_canary
from app.tests.conftest import signup

API = "/api/v1"
PID = "p" * 32


def good(**over: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": 1,
        "project_id": PID,
        "ref": "main",
        "checks": [
            {"kind": "sast", "status": "ran", "tool": {"name": "semgrep", "version": "1.2.3"}},
            {"kind": "secrets", "status": "ran", "tool": {"name": "gitleaks", "version": "8.0.0"}},
        ],
        "findings": [
            {
                "kind": "sast",
                "rule_id": "python.lang.security.audit.eval",
                "severity": "high",
                "path": "app/main.py",
                "line": 10,
                "title": "Use of eval",
                "message": "eval() on user input",
            },
            {
                "kind": "secrets",
                "rule_id": "generic-api-key",
                "severity": "high",
                "path": "config/dev.env",
                "line": 3,
            },
        ],
    }
    doc.update(over)
    return doc


def refused(doc: Any) -> sm.SubmissionRejected:
    with pytest.raises(sm.SubmissionRejected) as info:
        sm.parse_submission(doc)
    return info.value


# --- schema -----------------------------------------------------------------------------------------------


def test_a_valid_submission_is_accepted_and_completed() -> None:
    out = sm.build_outcome(sm.parse_submission(good()))
    assert out.status is AppScanStatus.COMPLETED
    assert out.checks_run == ["sast", "secrets"] and out.checks_skipped == []
    assert {s["reported_by"] for s in out.scanners} == {"submitter"}
    assert len(out.findings) == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra="x"),
        lambda d: d.update(schema_version=2),
        lambda d: d.update(project_id="../etc"),
        lambda d: d.update(project_id="a" * 65),
        lambda d: d.update(checks=[]),
        lambda d: d.update(checks=[{"kind": "dependency", "status": "ran", "tool": {"name": "x"}}]),
        lambda d: d["findings"][0].update(severity="catastrophic"),
        lambda d: d["findings"][0].update(kind="dependency"),
        lambda d: d["findings"][0].update(line=0),
        lambda d: d["findings"][0].update(line="ten"),
        lambda d: d["findings"][0].update(path="/etc/passwd"),
        lambda d: d["findings"][0].update(path="../../x"),
        lambda d: d["findings"][0].update(path="C:\\Windows\\x"),
        lambda d: d["findings"][0].update(path="a\x00b"),
        lambda d: d["findings"][0].update(rule_id="bad rule; drop table"),
        lambda d: d["findings"][0].update(title="t" * 201),
        lambda d: d["findings"][0].update(unknown=1),
        lambda d: d["checks"][0]["tool"].update(name="<script>"),
    ],
)
def test_invalid_documents_are_refused_with_a_fixed_message(mutate: Any) -> None:
    doc = copy.deepcopy(good())
    mutate(doc)
    err = refused(doc)
    assert err.code in ("invalid", "malformed")
    assert "<script>" not in str(err) and "etc/passwd" not in str(err)


@pytest.mark.parametrize("bad", [None, [], "text", 5, [good()], {}])
def test_non_objects_and_empty_documents_are_refused(bad: Any) -> None:
    assert refused(bad).code in ("invalid", "malformed")


def test_too_many_findings_are_refused_not_silently_cut() -> None:
    doc = good()
    doc["findings"] = [doc["findings"][0]] * 5_001
    assert refused(doc).code == "invalid"


def test_deeply_nested_input_is_refused_without_crashing() -> None:
    deep: Any = {}
    node = deep
    for _ in range(500):
        node["a"] = {}
        node = node["a"]
    assert refused(deep).code in ("too_deep", "invalid", "malformed")


# --- secrets -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "where",
    [
        lambda d, s: d["findings"][0].update(message=f"password = {s}"),
        lambda d, s: d["findings"][0].update(title=f"token {s}"),
        lambda d, s: d["findings"][1].update(path=f"config/{s}.env"),
        lambda d, s: d.update(ref=s),
        lambda d, s: d["checks"][0].update(reason=s),
        lambda d, s: d.update({s: 1}),
        lambda d, s: d["findings"][1].update(rule_id="x", message=s),
    ],
)
def test_a_secret_anywhere_refuses_the_whole_submission_and_is_never_echoed(where: Any) -> None:
    secret = make_canary()
    doc = copy.deepcopy(good())
    where(doc, secret)
    try:
        sm.parse_submission(doc)
    except sm.SubmissionRejected as err:
        assert_no_canary(secret, str(err), repr(err), err.code)
        assert err.code in ("contains_secret", "invalid")
    else:
        pytest.fail("a submission with a secret in it was accepted")


def test_a_known_token_shape_is_refused_with_the_contains_secret_code() -> None:
    doc = good()
    doc["findings"][0]["message"] = (
        "key AKIA" + "ABCDEFGHIJKLMNOP leaked"
    )  # split so the repo scan stays clean
    err = refused(doc)
    assert err.code == "contains_secret"
    assert "AKIA" not in str(err)


def test_secret_findings_never_keep_the_submitters_text() -> None:
    doc = good()
    doc["findings"][1]["title"] = "my custom title"
    doc["findings"][1]["message"] = "some detail the tool added"
    out = sm.build_outcome(sm.parse_submission(doc))
    finding = next(f for f in out.findings if f.kind == "secrets")
    assert isinstance(finding, CodeFinding)
    assert finding.title == sm.EXPOSED_TITLE and finding.evidence is None
    assert "custom" not in finding.title + finding.description
    assert "rotate" in finding.remediation


# --- honest status -----------------------------------------------------------------------------------------


def test_a_skipped_check_makes_the_result_incomplete_and_says_why() -> None:
    doc = good()
    doc["checks"][1] = {
        "kind": "secrets",
        "status": "skipped",
        "reason": "tool crashed",
        "tool": {"name": "gitleaks"},
    }
    doc["findings"] = [doc["findings"][0]]
    out = sm.build_outcome(sm.parse_submission(doc))
    assert out.status is AppScanStatus.INCOMPLETE
    assert any("tool crashed" in s["reason"] for s in out.checks_skipped)


def test_no_check_ran_is_incomplete_never_complete_or_clean() -> None:
    doc = good()
    doc["checks"] = [{"kind": "sast", "status": "skipped", "tool": {"name": "semgrep"}}]
    doc["findings"] = []
    out = sm.build_outcome(sm.parse_submission(doc))
    assert out.status is AppScanStatus.INCOMPLETE and out.checks_run == []


def test_findings_for_a_check_that_did_not_run_are_not_trusted() -> None:
    doc = good()
    doc["checks"] = [doc["checks"][0]]  # only sast ran
    out = sm.build_outcome(sm.parse_submission(doc))
    assert [f.kind for f in out.findings] == ["sast"]
    assert any(s["check"] == "secrets" for s in out.checks_skipped)


def test_fingerprints_ignore_line_numbers_and_distinguish_repeats() -> None:
    a = good()
    b = copy.deepcopy(a)
    b["findings"][0]["line"] = 99
    fa = sm.build_outcome(sm.parse_submission(a)).findings
    fb = sm.build_outcome(sm.parse_submission(b)).findings
    assert [f.fingerprint for f in fa] == [f.fingerprint for f in fb]
    twice = good()
    twice["findings"].append(copy.deepcopy(twice["findings"][0]) | {"line": 40})
    prints = [f.fingerprint for f in sm.build_outcome(sm.parse_submission(twice)).findings]
    assert len(prints) == len(set(prints)) == 3


def test_hostile_text_is_kept_as_text_and_cleaned() -> None:
    doc = good()
    doc["findings"][0]["title"] = "<img src=x onerror=alert(1)>\x1b[31m"
    doc["findings"][0]["message"] = "line1\x00line2 <script>alert(1)</script>"
    finding = sm.build_outcome(sm.parse_submission(doc)).findings[0]
    assert "\x00" not in finding.description and "\x1b" not in finding.title
    assert "<script>" in finding.description  # escaping happens at render time; the data stays text


# --- storage -----------------------------------------------------------------------------------------------


@pytest.fixture
def stored(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings: Settings = make_settings(default_plan=None)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        engine = client.app.state.s.engine  # type: ignore[attr-defined]
        repo = AppScanRepository(engine)
        org = client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
        yield client, repo, org, repo.create_project(org, None, "shop", "upload", None)


def test_code_findings_are_stored_and_read_back_with_line_and_no_package_fields(stored: Any) -> None:
    client, repo, org, project = stored
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["sast", "secrets"], [], 100, start, None).scan_id
    doc = good(project_id=project)
    assert repo.store_result(org, scan, sm.build_outcome(sm.parse_submission(doc)))
    rows = repo.get_findings(org, scan)
    assert {r.kind for r in rows} == {"sast", "secrets"}
    sast = next(r for r in rows if r.kind == "sast")
    assert sast.path == "app/main.py" and sast.line == 10 and sast.package_name is None
    run = repo.get_run(org, scan)
    assert run is not None and run.status == "completed"
    assert repo.usage(org, start).runs == 1


def test_a_canary_in_every_text_field_never_reaches_the_database(stored: Any) -> None:
    client, repo, org, project = stored
    secret = make_canary()
    doc = good(project_id=project)
    # Even if a secret slipped past the first check, nothing stored carries it: secret findings drop the text,
    # and the other fields are redacted on write. Here it is placed where only the stored copy is exposed.
    start, _ = current_period(datetime.now(UTC))
    scan = repo.accept_run(org, project, None, ["sast"], [], 100, start, None).scan_id
    outcome = sm.build_outcome(sm.parse_submission(doc))
    original = outcome.findings[0]
    assert isinstance(original, CodeFinding)
    injected = dataclasses.replace(original, evidence=f"password = {secret}")
    assert injected.evidence and secret in injected.evidence  # the test really injects it
    outcome.findings[0] = injected
    repo.store_result(org, scan, outcome)
    with client.app.state.s.engine.connect() as conn:
        values = [str(v) for row in conn.execute(select(AppFindingRow.__table__)).all() for v in row]
    assert_no_canary(secret, json.dumps(values))


def test_parsing_a_large_valid_submission_is_fast() -> None:
    doc = good()
    doc["findings"] = [
        {
            "kind": "sast",
            "rule_id": f"rule.{i % 50}",
            "severity": "low",
            "path": f"src/f{i}.py",
            "line": i + 1,
            "title": "t",
            "message": "m",
        }
        for i in range(5_000)
    ]
    started = time.perf_counter()
    out = sm.build_outcome(sm.parse_submission(doc))
    assert len(out.findings) == 5_000
    assert time.perf_counter() - started < 10
