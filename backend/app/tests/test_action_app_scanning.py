"""The App Scanning GitHub Action (action/app-scanning/submit.py): SARIF conversion, safety rules and the full
path to the real submission route. The HTTP call is replaced by a call into the application itself, so the real
route, token checks, secret check and accounting are exercised without a network."""

# ruff: noqa: F811
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from app.models.app_scan import AppFindingRow, AppScanRow
from app.tests.canary import make_canary
from app.tests.test_appscan_ci_tokens import APP, dump_tables, env, rows, usage  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "action" / "app-scanning" / "submit.py"
_spec = importlib.util.spec_from_file_location("app_scanning_action", SCRIPT)
assert _spec and _spec.loader
action = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(action)


def sarif(
    results: list[dict[str, Any]], tool: str = "Semgrep", version: str = "1.50.0", rules: Any = None
) -> dict[str, Any]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": tool, "semanticVersion": version, "rules": rules or []}},
                "results": results,
            }
        ],
    }


def result(
    rule: str = "py.sql", level: str = "error", uri: str = "src/db.py", line: int | None = 12, **kw: Any
) -> dict[str, Any]:
    region = {"startLine": line} if line is not None else {}
    out: dict[str, Any] = {
        "ruleId": rule,
        "level": level,
        "message": {"text": "SQL built from input"},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}, "region": region}}],
    }
    out.update(kw)
    return out


def write(tmp_path: Path, name: str, document: Any) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


# --- conversion ------------------------------------------------------------------------------------------


def test_levels_and_scores_map_to_severities() -> None:
    converted = action.convert(
        sarif(
            [
                result("a", "error"),
                result("b", "warning"),
                result("c", "note"),
                result("d", "none"),
                result("e", "note", properties={"security-severity": "9.8"}),
                result("f", "error", properties={"security-severity": "5.0"}),
                result("g", "error", properties={"security-severity": "0"}),
            ]
        ),
        "sast",
    )
    found = converted.findings
    assert [f["severity"] for f in found] == ["high", "medium", "low", "info", "critical", "medium", "info"]


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("src/a.py", "src/a.py"),
        ("./src/a.py", "src/a.py"),
        ("file://src/dir%20x/a.py", "src/dir x/a.py"),
        ("src\\win\\a.py", "src/win/a.py"),
        ("/etc/passwd", None),
        ("../../secret", None),
        ("a/../b", None),
        ("C:\\x\\a.py", None),
        ("a\x00b", None),
        ("", None),
    ],
)
def test_paths_are_made_safe_or_dropped(uri: str, expected: str | None) -> None:
    assert action.safe_path(uri) == expected


def test_results_without_a_usable_rule_or_path_are_counted_not_sent() -> None:
    results: list[Any] = [result("ok"), result("bad", uri="/abs/path.py"), {"message": {"text": "x"}}, "junk"]
    converted = action.convert(sarif(results), "sast")
    assert [f["rule_id"] for f in converted.findings] == ["ok"] and converted.unusable == 3


def test_a_secret_finding_carries_only_rule_file_and_line() -> None:
    canary = make_canary()
    leaky = result(
        "generic-api-key",
        uri="config/.env",
        line=3,
        message={"text": f"key = {canary}"},
        partialFingerprints={"commitSha": "abc"},
    )
    leaky["locations"][0]["physicalLocation"]["region"]["snippet"] = {"text": canary}
    converted = action.convert(sarif([leaky], tool="gitleaks"), "secrets")
    found = converted.findings
    assert found == [
        {
            "kind": "secrets",
            "rule_id": "generic-api-key",
            "severity": "high",
            "confidence": "medium",
            "path": "config/.env",
            "line": 3,
        }
    ]
    assert canary not in json.dumps(found)


def test_tool_names_rule_ids_and_text_are_cleaned() -> None:
    converted = action.convert(
        sarif([result("we ird/rule\n::x", uri="a.py")], tool="Se<m>grep!", version="1.0;rm"), "sast"
    )
    assert converted.tool == {"name": "Semgrep", "version": "1.0rm"}
    assert converted.findings[0]["rule_id"] == "we_ird/rule_::x"


def test_too_many_findings_keeps_the_worst_and_says_so(tmp_path: Path) -> None:
    results = [result(f"r{i}", "note", line=i + 1) for i in range(5000)] + [result("worst", "error")]
    path = write(tmp_path, "s.sarif", sarif(results))
    document, notes = action.build("p1", path, "", "")
    assert len(document["findings"]) == 5000 and document["findings"][0]["rule_id"] == "worst"
    assert any("left out" in n for n in notes)


def test_a_missing_file_is_a_skipped_check_and_no_input_is_an_error(tmp_path: Path) -> None:
    document, notes = action.build("p1", str(tmp_path / "none.sarif"), "", "")
    assert document["checks"][0]["status"] == "skipped" and notes
    with pytest.raises(action.Stop):
        action.build("p1", "", "", "")


def test_a_file_that_is_not_json_or_not_sarif_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sarif"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(action.Stop):
        action.build("p1", str(bad), "", "")
    with pytest.raises(action.Stop):
        action.convert({"nope": 1}, "sast")


# --- the whole path through the real route -------------------------------------------------------------------


def run_action(
    client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str, project: str, **inputs: str
) -> tuple[int, str]:
    sent: list[bytes] = []

    def post(url: str, bearer: str, key: str, body: bytes) -> tuple[int, dict[str, Any], str]:
        sent.append(body)
        response = bare_post(client, url, bearer, key, body)
        return response.status_code, response.json(), response.headers.get("retry-after", "")

    monkeypatch.setattr(action, "post", post)
    out = tmp_path / "out.txt"
    environment = {
        "SS_API_KEY": token,
        "SS_PROJECT_ID": project,
        "SS_API_URL": "http://localhost/api/v1",
        "GITHUB_RUN_ID": "99",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "0123456789abcdef",
        "GITHUB_REF_NAME": "main",
        "GITHUB_OUTPUT": str(out),
        **{f"SS_{k.upper()}": v for k, v in inputs.items()},
    }
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = action.main(environment, lambda _s: None)
    return code, buffer.getvalue() + (out.read_text() if out.exists() else "")


def bare_post(client: Any, url: str, token: str, key: str, body: bytes) -> Any:
    from app.tests.test_integrations import bare

    path = url.split("localhost", 1)[1]
    return bare(client)._call(
        "post",
        path,
        content=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key,
            "Content-Type": "application/json",
        },
    )


def test_a_clean_run_passes_and_is_counted_once(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    sast = write(tmp_path, "a.sarif", sarif([]))
    secrets = write(tmp_path, "b.sarif", sarif([], tool="gitleaks", version="8.18.0"))
    code, output = run_action(
        client, tmp_path, monkeypatch, token, pid, sast_sarif=sast, secrets_sarif=secrets
    )
    assert code == 0 and "passed=true" in output and "result=completed_no_findings" in output
    assert usage(client) == 1
    # The same pipeline run again is the same run: nothing new is counted.
    code, output = run_action(
        client, tmp_path, monkeypatch, token, pid, sast_sarif=sast, secrets_sarif=secrets
    )
    assert code == 0 and "already submitted" in output and usage(client) == 1


def test_a_high_finding_fails_the_job_unless_the_rule_allows_it(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    sast = write(tmp_path, "a.sarif", sarif([result()]))
    secrets = write(tmp_path, "b.sarif", sarif([], tool="gitleaks"))
    code, output = run_action(
        client, tmp_path, monkeypatch, token, pid, sast_sarif=sast, secrets_sarif=secrets
    )
    assert code == 1 and "1 high finding(s)" in output and "passed=false" in output
    code, _ = run_action(
        client, tmp_path, monkeypatch, token, pid, sast_sarif=sast, secrets_sarif=secrets, fail_on="critical"
    )
    assert code == 0
    assert len(rows(client, AppFindingRow)) >= 1


def test_a_check_that_did_not_run_is_incomplete_and_fails_even_with_fail_on_none(  # type: ignore[no-untyped-def]
    env, tmp_path, monkeypatch
) -> None:
    client, pid, token, _w = env
    sast = write(tmp_path, "a.sarif", sarif([]))
    code, output = run_action(
        client,
        tmp_path,
        monkeypatch,
        token,
        pid,
        sast_sarif=sast,
        secrets_sarif=str(tmp_path / "missing"),
        fail_on="none",
    )
    assert code == 1 and "result=incomplete" in output and "incomplete" in output


def test_a_secret_value_in_the_sarif_never_reaches_the_server(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    canary = make_canary()
    leaky = result("generic-api-key", uri="config/.env", line=3, message={"text": f"password = {canary}"})
    leaky["locations"][0]["physicalLocation"]["region"]["snippet"] = {"text": canary}
    secrets = write(tmp_path, "b.sarif", sarif([leaky], tool="gitleaks"))
    code, output = run_action(client, tmp_path, monkeypatch, token, pid, secrets_sarif=secrets)
    assert code == 1  # a hardcoded secret is high severity
    assert canary not in output
    assert canary not in dump_tables(client, "app_scans", "app_findings", "audit_events")


def test_the_token_is_masked_and_never_printed(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    sast = write(tmp_path, "a.sarif", sarif([]))
    _code, output = run_action(client, tmp_path, monkeypatch, token, pid, sast_sarif=sast)
    assert output.count(token) == 1 and f"::add-mask::{token}" in output


def test_refusals_are_explained_without_echoing_anything(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, web_token = env
    sast = write(tmp_path, "a.sarif", sarif([]))
    code, output = run_action(client, tmp_path, monkeypatch, web_token, pid, sast_sarif=sast)
    assert code == 2 and "Web Scanning token" in output and web_token not in output
    # A token the server does not know (or a revoked one) is a 401 from the server itself.
    code, output = run_action(client, tmp_path, monkeypatch, "ssa_" + "x" * 30, pid, sast_sarif=sast)
    assert code == 2 and "answered 401" in output
    code, output = run_action(client, tmp_path, monkeypatch, token, "doesnotexist", sast_sarif=sast)
    assert code == 2 and "answered 404" in output
    assert rows(client, AppScanRow) == [] and usage(client) == 0


def test_bad_settings_are_refused_before_anything_is_sent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(action, "post", lambda *a: pytest.fail("nothing may be sent"))
    base = {"SS_API_KEY": "ssa_x", "SS_PROJECT_ID": "p1", "SS_SAST_SARIF": str(tmp_path / "x")}
    for change in (
        {"SS_API_URL": "http://evil.example/api"},
        {"SS_API_URL": "http://localhost.evil.example/api"},
        {"SS_FAIL_ON": "banana"},
        {"SS_PROJECT_ID": "../x"},
        {"SS_API_KEY": ""},
    ):
        assert action.main({**base, **change}) == 2


def test_workflow_commands_in_text_are_neutralised() -> None:
    assert "::" not in action.clean("::set-output name=x::y\n::error::boom")


def test_503_is_retried_with_the_server_s_wait_and_then_succeeds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    answers = iter([(503, {}, "7"), (0, {}, ""), (201, {"id": "x"}, "")])
    monkeypatch.setattr(action, "post", lambda *a: next(answers))
    waits: list[int] = []
    status, body = action.submit("https://x/api/v1", "t", "k", b"{}", waits.append)
    assert status == 201 and body == {"id": "x"} and waits == [7, 15]


def test_the_request_is_never_redirected_to_another_host() -> None:
    """A 302 makes urllib repeat the request as a GET with the same headers, token included, unless refused."""
    stolen: list[str | None] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            stolen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    target = HTTPServer(("127.0.0.1", 0), Target)

    class Redirector(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/stolen")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    redirector = HTTPServer(("127.0.0.1", 0), Redirector)
    for server in (target, redirector):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        status, _body, _retry = action.post(
            f"http://127.0.0.1:{redirector.server_port}/api/v1/app/ci/submissions", "tok", "k", b"{}"
        )
    finally:
        target.shutdown()
        redirector.shutdown()
    assert status == 302 and stolen == []


# --- final review: malformed input, limits, strict answers, settings ---------------------------------------------


MALFORMED: list[Any] = [
    {"runs": "x"},
    {"runs": [None, 1, "x", []]},
    {"runs": [{"tool": "x", "results": "x"}]},
    {"runs": [{"tool": {"driver": "x"}, "results": [None, 1, "x", [], {}]}]},
    {"runs": [{"tool": {"driver": {"rules": "x"}}, "results": [{"ruleId": "r", "locations": "x"}]}]},
    {"runs": [{"results": [{"ruleId": "r", "locations": [None]}]}]},
    {"runs": [{"results": [{"ruleId": "r", "locations": [{"physicalLocation": "x"}]}]}]},
    {"runs": [{"results": [{"ruleId": "r", "locations": [{"physicalLocation": {"artifactLocation": []}}]}]}]},
    {
        "runs": [
            {"results": [{"ruleId": 5, "message": "x", "level": [], "properties": "x", "suppressions": 1}]}
        ]
    },
    {
        "runs": [
            {
                "results": [
                    {
                        "ruleId": "r",
                        "properties": {"security-severity": "nan"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "a.py"},
                                    "region": {"startLine": True},
                                }
                            }
                        ],
                    }
                ]
            }
        ]
    },
    {
        "runs": [
            {
                "results": [
                    {
                        "ruleId": "r",
                        "properties": {"security-severity": [1]},
                        "locations": [
                            {"physicalLocation": {"artifactLocation": {"uri": "a.py"}, "region": []}}
                        ],
                    }
                ]
            }
        ]
    },
    {"runs": [{"invocations": "x", "results": []}]},
]


@pytest.mark.parametrize("document", MALFORMED)
def test_malformed_sarif_never_raises_and_never_sends_garbage(document: Any) -> None:
    for kind in ("sast", "secrets"):
        try:
            converted = action.convert(document, kind)
        except action.Stop:
            continue
        for finding in converted.findings:
            assert finding["rule_id"] and finding["path"] and finding["severity"] in action.SEVERITIES


def test_unreadable_files_are_refused_with_exit_2_not_a_traceback(tmp_path: Path) -> None:
    deep = tmp_path / "deep.sarif"
    deep.write_text("[" * 200_000, encoding="utf-8")  # json.load would hit the recursion limit
    huge = tmp_path / "huge.sarif"
    huge.write_bytes(b" " * (action.MAX_SARIF_BYTES + 1))
    binary = tmp_path / "binary.sarif"
    binary.write_bytes(b"\xff\xfe\x00\x80")
    for path in (deep, huge, binary, tmp_path):  # the last is a directory
        with pytest.raises(action.Stop):
            action.load(str(path))
    env = {"SS_API_KEY": "ssa_" + "k" * 30, "SS_PROJECT_ID": "p1", "SS_SAST_SARIF": str(deep)}
    assert action.main(env, lambda _s: None) == 2


def test_a_sarif_without_runs_or_with_a_failed_tool_is_a_skipped_check(tmp_path: Path) -> None:
    empty = write(tmp_path, "empty.sarif", {"version": "2.1.0", "runs": []})
    failed_doc = sarif([result()])
    failed_doc["runs"][0]["invocations"] = [{"executionSuccessful": False}]
    failed = write(tmp_path, "failed.sarif", failed_doc)
    document, notes = action.build("p1", empty, failed, "")
    assert [c["status"] for c in document["checks"]] == ["skipped", "skipped"]
    assert document["findings"] == [] and len(notes) == 2  # a failed tool's findings are not trusted


def test_suppressed_results_are_left_out_and_counted() -> None:
    suppressed = result("r1", suppressions=[{"kind": "inSource"}])
    converted = action.convert(sarif([suppressed, result("r2")]), "sast")
    assert [f["rule_id"] for f in converted.findings] == ["r2"] and converted.suppressed == 1


def test_only_the_first_results_are_read_and_the_rest_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(action, "MAX_RESULTS_READ", 3)
    converted = action.convert(sarif([result(f"r{i}") for i in range(10)]), "sast")
    assert len(converted.findings) == 3 and converted.left_out == 7


def test_a_submission_is_kept_under_the_servers_4_mib_limit(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    long_text = "x" * 1000
    results = [
        result(f"r{i}", "error", uri=f"src/file{i}.py", line=i + 1, message={"text": long_text})
        for i in range(5000)
    ]
    path = write(tmp_path, "big.sarif", sarif(results))
    document, notes = action.build(pid, path, "", "")
    body = action.encode(document, notes)
    assert len(body) <= action.MAX_BODY_BYTES and len(body) < 4 * 1024 * 1024
    assert any("shortened" in n or "left out" in n for n in notes)
    code, output = run_action(client, tmp_path, monkeypatch, token, pid, sast_sarif=path)
    assert code == 1 and "answered" not in output  # accepted by the real route, then failed on the findings


def test_only_a_clearly_completed_answer_can_pass(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env = {"SS_API_KEY": "ssa_" + "k" * 30, "SS_PROJECT_ID": "p1", "SS_API_URL": "http://localhost/api/v1"}
    sast = "sast.sarif"

    def attempt(answer: tuple[int, dict[str, Any], str], tmp: Path) -> int:
        path = write(tmp, sast, sarif([]))
        monkeypatch.setattr(action, "post", lambda *a: answer)
        return int(action.main({**env, "SS_SAST_SARIF": path}, lambda _s: None))

    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        good = {"id": "abc123", "result": "completed_no_findings", "counts": {}}
        assert attempt((201, good, ""), tmp) == 0
        assert attempt((201, {}, ""), tmp) == 2  # an empty 201 (for example from a proxy) never passes
        assert attempt((201, {"id": "abc123"}, ""), tmp) == 2
        assert attempt((201, {"id": "../x", "result": "completed_no_findings"}, ""), tmp) == 2
        for label in ("scanner_error", "interrupted", "cancelled", "failed", "queued", "something_new"):
            assert attempt((201, {**good, "result": label}, ""), tmp) == 1, label
        assert attempt((200, good, ""), tmp) == 2  # only 201 is a created run
        assert attempt((500, {}, ""), tmp) == 2


def test_eight_attempts_then_exit_2_with_a_clear_message(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    path = write(tmp_path, "a.sarif", sarif([]))
    calls: list[int] = []

    def unreachable(*args: Any) -> tuple[int, dict[str, Any], str]:
        calls.append(1)
        return 0, {}, ""

    monkeypatch.setattr(action, "post", unreachable)
    waits: list[int] = []
    env = {"SS_API_KEY": "ssa_" + "k" * 30, "SS_PROJECT_ID": "p1", "SS_SAST_SARIF": path}
    assert action.main(env, waits.append) == 2
    assert len(calls) == 8 and len(waits) == 7
    assert "server not reachable" in capsys.readouterr().out


def test_settings_that_could_forward_the_token_elsewhere_are_refused(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(action, "post", lambda *a: pytest.fail("nothing may be sent"))
    base = {"SS_API_KEY": "ssa_" + "k" * 30, "SS_PROJECT_ID": "p1", "SS_SAST_SARIF": "x"}
    for url in (
        "http://api.example.com/api/v1",
        "https://user:pw@getsecurescope.com/api/v1",
        "https://getsecurescope.com/api/v1?next=https://evil.example",
        "https://getsecurescope.com/api/v1#x",
        "http://localhost.evil.example/api",
        "http://127.0.0.1.evil.example/api",
        "file:///etc/passwd",
        "ftp://x/y",
        "https://",
        "https://exa mple.com/api",
        "https://example.com/\nHost: evil",
    ):
        assert action.main({**base, "SS_API_URL": url}, lambda _s: None) == 2, url
    for token in ("", "short", "ssa_with space123", "ssa_line\nbreak123", "ssk_" + "k" * 30):
        assert action.main({**base, "SS_API_KEY": token}, lambda _s: None) == 2, token


def test_a_different_host_is_allowed_only_with_a_visible_warning(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    path = write(tmp_path, "a.sarif", sarif([]))
    sent: list[str] = []

    def recording(url: str, *args: Any) -> tuple[int, dict[str, Any], str]:
        sent.append(url)
        return 201, {"id": "a1", "result": "completed_no_findings"}, ""

    monkeypatch.setattr(
        action,
        "post",
        recording,
    )
    env = {
        "SS_API_KEY": "ssa_" + "k" * 30,
        "SS_PROJECT_ID": "p1",
        "SS_SAST_SARIF": path,
        "SS_API_URL": "https://eu.example.com/api/v1",
    }
    assert action.main(env, lambda _s: None) == 0
    assert "will be sent to eu.example.com" in capsys.readouterr().out and sent == [
        "https://eu.example.com/api/v1/app/ci/submissions"
    ]


def test_an_unexpected_defect_is_exit_2_with_a_fixed_message_and_no_input_text(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch, capsys
) -> None:
    canary = make_canary()
    path = write(tmp_path, "a.sarif", sarif([]))

    def boom(*args: Any) -> Any:
        raise RuntimeError(f"internal {canary}")

    monkeypatch.setattr(action, "build", boom)
    env = {"SS_API_KEY": "ssa_" + "k" * 30, "SS_PROJECT_ID": "p1", "SS_SAST_SARIF": path}
    assert action.main(env, lambda _s: None) == 2
    out = capsys.readouterr()
    assert canary not in out.out + out.err and "unexpected error (RuntimeError)" in out.out


def test_both_scanners_missing_is_incomplete_through_the_real_route(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    code, output = run_action(
        client,
        tmp_path,
        monkeypatch,
        token,
        pid,
        sast_sarif=str(tmp_path / "a"),
        secrets_sarif=str(tmp_path / "b"),
        fail_on="none",
    )
    assert code == 1 and "result=incomplete" in output
    assert usage(client) == 1  # an accepted run counts, even though nothing was checked


def test_output_values_cannot_inject_lines_into_the_outputs_file(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write(tmp_path, "a.sarif", sarif([]))
    out = tmp_path / "o.txt"
    monkeypatch.setattr(
        action,
        "post",
        lambda *a: (201, {"id": "abc", "result": "completed_no_findings\nevil=1", "result_text": "x::y"}, ""),
    )
    env_ = {
        "SS_API_KEY": "ssa_" + "k" * 30,
        "SS_PROJECT_ID": "p1",
        "SS_SAST_SARIF": path,
        "GITHUB_OUTPUT": str(out),
    }
    action.main(env_, lambda _s: None)
    assert out.read_text().splitlines() == [
        "scan-id=abc",
        "result=completed_no_findings evil=1",
        "passed=false",
    ]


# --- genuine tool output ---------------------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sarif"


def test_genuine_semgrep_output_converts_and_no_source_leaves_the_runner() -> None:
    """semgrep-1.182.1.sarif was written by Semgrep OSS 1.182.1 (local rules, no network) on a two-file sample
    with an SQL string-formatting call and an os.system call. It contains the matched source lines in
    `snippet`; none of that may be in the submission."""
    raw = (FIXTURES / "semgrep-1.182.1.sarif").read_text(encoding="utf-8")
    assert "SELECT * FROM users" in raw  # the genuine file does carry source code
    converted = action.convert(json.loads(raw), "sast")
    assert converted.tool == {"name": "Semgrep OSS", "version": "1.182.1"}
    assert [(f["rule_id"], f["severity"], f["path"], f["line"]) for f in converted.findings] == [
        ("demo.sql-string-format", "high", "src/db.py", 6),
        ("demo.os-system", "medium", "src/db.py", 12),
    ]
    sent = json.dumps(converted.findings)
    assert "SELECT" not in sent and "snippet" not in sent and "os.system(cmd)" not in sent


def test_genuine_semgrep_output_goes_through_the_real_route(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    code, output = run_action(
        client, tmp_path, monkeypatch, token, pid, sast_sarif=str(FIXTURES / "semgrep-1.182.1.sarif")
    )
    assert code == 1 and "result=incomplete" not in output  # a high finding, and the only check ran
    stored = rows(client, AppFindingRow)
    assert len(stored) == 2
    assert "SELECT" not in dump_tables(client, "app_findings", "app_scans")


def test_genuine_gitleaks_output_is_a_high_finding_with_only_rule_file_and_line() -> None:
    """gitleaks-8.18.4-redacted.sarif was written by Gitleaks 8.18.4 (`--redact`, no git history) on a file with
    a randomly generated fake GitHub token. Genuine Gitleaks SARIF has no `level`, which must not read as medium."""
    converted = action.convert(
        json.loads((FIXTURES / "gitleaks-8.18.4-redacted.sarif").read_text()), "secrets"
    )
    assert converted.tool["name"] == "gitleaks"
    assert converted.findings == [
        {
            "kind": "secrets",
            "rule_id": "github-pat",
            "severity": "high",
            "confidence": "medium",
            "path": "config/.env",
            "line": 1,
        }
    ]


def test_an_unredacted_genuine_gitleaks_file_never_leaks_the_value(tmp_path: Path) -> None:
    """Without `--redact` Gitleaks puts the matched value in the message and the snippet. The only difference from
    the committed redacted file is that text, so the value is swapped in here and followed through the action."""
    canary = make_canary()
    raw = (FIXTURES / "gitleaks-8.18.4-redacted.sarif").read_text(encoding="utf-8")
    assert "REDACTED" in raw
    leaky = raw.replace("REDACTED", canary)
    assert canary in leaky
    path = tmp_path / "gitleaks.sarif"
    path.write_text(leaky, encoding="utf-8")
    document, notes = action.build("p1", "", str(path), "")
    assert canary not in action.encode(document, notes).decode()


def test_genuine_gitleaks_output_goes_through_the_real_route(env, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client, pid, token, _w = env
    code, output = run_action(
        client,
        tmp_path,
        monkeypatch,
        token,
        pid,
        secrets_sarif=str(FIXTURES / "gitleaks-8.18.4-redacted.sarif"),
    )
    assert code == 1  # high severity, so fail-on high stops the job
    stored = rows(client, AppFindingRow)
    assert len(stored) == 1 and stored[0].severity == "high" and stored[0].kind == "secrets"


def _serve(status: int, body: bytes, content_type: str, seen: list[str | None]) -> tuple[HTTPServer, str]:
    class Answer(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append(self.headers.get("User-Agent"))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/api/v1"


def test_a_403_that_is_not_the_plan_limit_is_not_called_a_used_up_allowance() -> None:
    """A firewall page (HTML, no JSON detail) must not be reported as an exhausted allowance."""
    seen: list[str | None] = []
    server, base = _serve(
        403, b"<html><body><h1>Access denied</h1> Error 1010</body></html>", "text/html", seen
    )
    try:
        status, body, _retry = action.post(f"{base}/app/ci/submissions", "ssa_" + "x" * 30, "k", b"{}")
    finally:
        server.shutdown()
    message = action.explain(status, body)
    assert status == 403
    assert "used up" not in message and "allowance" not in message
    assert "not from the SecureScope API" in message and "Access denied" in message
    assert seen == ["SecureScope-App-Action/1"]  # not Python's default, which firewalls often refuse


def test_a_real_plan_limit_is_shown_as_the_server_worded_it() -> None:
    detail = "Your plan includes 5 App Scanning runs per month and they are used up. Upgrade or wait."
    message = action.explain(403, {"detail": detail})
    assert message.startswith("SecureScope answered 403: the request was refused.") and detail in message
