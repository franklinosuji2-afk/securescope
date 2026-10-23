"""The GitHub Action script, run for real against a fake local SecureScope API."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "action" / "scan.sh"
pytestmark = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("jq") and shutil.which("curl") and SCRIPT.exists()),
    reason="needs bash, curl, jq and the action folder",
)

Factory = Callable[[tuple[int, Any], list[tuple[int, Any]]], "Fake"]
SCAN_ID = "a1b2c3d4e5f60718"


def _scan(status: str = "completed", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": SCAN_ID,
        "host": "example.com",
        "status": status,
        "score": 82,
        "grade": "B",
        "counts": {},
        "findings": [{"id": "HDR-1", "severity": "medium", "title": "Missing header"}],
        "error": None,
        "link": "https://getsecurescope.com/#/findings?scan=" + SCAN_ID,
    }
    base.update(over)
    return base


class Fake:
    def __init__(self, post: tuple[int, Any], gets: list[tuple[int, Any]]) -> None:
        self.post = post
        self.gets = list(gets)
        self.auth: list[str | None] = []
        self.posted: list[Any] = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code: int, body: Any) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:  # noqa: N802
                fake.auth.append(self.headers.get("Authorization"))
                n = int(self.headers.get("Content-Length", "0"))
                fake.posted.append(json.loads(self.rfile.read(n) or b"{}"))
                self._send(*fake.post)

            def do_GET(self) -> None:  # noqa: N802
                fake.auth.append(self.headers.get("Authorization"))
                item = fake.gets.pop(0) if len(fake.gets) > 1 else fake.gets[0]
                self._send(*item)

            def log_message(self, *a: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def run(tmp_path: Path, fake: Fake, **env: str) -> tuple[int, str, dict[str, str], str]:
    out, summary = tmp_path / "out", tmp_path / "summary"
    out.write_text("")
    summary.write_text("")
    e = {
        "PATH": os.environ["PATH"],
        "SS_API_KEY": "ssk_secrettoken123",
        "SS_URL": "https://example.com",
        "SS_API_URL": fake.url,
        "SS_POLL_SECONDS": "0",
        "SS_RETRY_SECONDS": "0",
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    e.update(env)
    p = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, timeout=60, check=False)
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return p.returncode, p.stdout + p.stderr, outputs, summary.read_text()


@pytest.fixture
def fake_factory() -> Iterator[Callable[[tuple[int, Any], list[tuple[int, Any]]], Fake]]:
    made: list[Fake] = []

    def make(post: tuple[int, Any], gets: list[tuple[int, Any]]) -> Fake:
        f = Fake(post, gets)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


def test_passes_and_sets_outputs(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory(
        (202, _scan("queued", score=None, grade=None)),
        [(200, _scan("running", score=None, grade=None)), (200, _scan())],
    )
    code, log, outputs, summary = run(tmp_path, f, SS_FAIL_ON="high", SS_MIN_SCORE="70")
    assert code == 0, log
    assert outputs == {"scan-id": SCAN_ID, "score": "82", "grade": "B", "passed": "true"}
    assert "not proof" in log
    assert "Score 82/100" in summary
    assert f.posted == [{"url": "https://example.com"}]
    assert set(f.auth) == {"Bearer ssk_secrettoken123"}


def test_token_never_printed(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory((202, _scan()), [(200, _scan())])
    _, log, _, summary = run(tmp_path, f)
    # The only mention is the mask command, which tells the runner to hide the value.
    shown = [ln for ln in log.splitlines() if not ln.startswith("::add-mask::")]
    assert "secrettoken123" not in "\n".join(shown) + summary


def test_fails_on_low_score(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory((202, _scan()), [(200, _scan())])
    code, log, outputs, _ = run(tmp_path, f, SS_MIN_SCORE="90")
    assert code == 1
    assert outputs["passed"] == "false"
    assert "below the minimum" in log


def test_fails_on_severity(tmp_path: Path, fake_factory: Factory) -> None:
    s = _scan(findings=[{"id": "TLS-1", "severity": "high", "title": "Old TLS"}])
    f = fake_factory((202, s), [(200, s)])
    code, log, _, _ = run(tmp_path, f, SS_FAIL_ON="high")
    assert code == 1
    assert "severity high or higher" in log
    f2 = fake_factory((202, s), [(200, s)])
    code2, _, outputs2, _ = run(tmp_path, f2, SS_FAIL_ON="none")
    assert code2 == 0
    assert outputs2["passed"] == "true"


def test_workflow_commands_in_titles_are_defused(tmp_path: Path, fake_factory: Factory) -> None:
    evil = "::set-output name=x::1\n::error::pwned <img src=x> `tick`"
    s = _scan(findings=[{"id": "X-1", "severity": "low", "title": evil}])
    f = fake_factory((202, s), [(200, s)])
    code, log, _, summary = run(tmp_path, f)
    assert code == 0
    assert not any(
        line.lstrip().startswith("::")
        for line in log.splitlines()
        if "error::SecureScope" not in line and not line.startswith("::add-mask::")
    )
    assert "<img" not in summary


def test_bad_token_is_an_operational_error(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory((401, {"detail": "no"}), [(200, _scan())])
    code, log, outputs, _ = run(tmp_path, f)
    assert code == 2
    assert "not valid" in log
    assert outputs == {}


def test_plan_refusal_shows_reason(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory(
        (403, {"detail": "CI access is part of the Professional and Agency plans."}), [(200, _scan())]
    )
    code, log, _, _ = run(tmp_path, f)
    assert code == 2
    assert "Professional and Agency" in log


def test_failed_scan_is_not_a_pass(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory(
        (202, _scan("queued")), [(200, _scan("failed", score=None, grade=None, error="Site unreachable"))]
    )
    code, log, _, _ = run(tmp_path, f)
    assert code == 2
    assert "not a clean result" in log


def test_retries_while_backend_wakes(tmp_path: Path, fake_factory: Factory) -> None:
    f = fake_factory((503, {"detail": "waking"}), [(200, _scan())])
    code, log, _, _ = run(tmp_path, f)
    assert code == 2
    assert "Waiting for it to wake up" in log


@pytest.mark.parametrize(
    "env",
    [
        {"SS_API_KEY": ""},
        {"SS_URL": "ftp://example.com"},
        {"SS_MIN_SCORE": "abc"},
        {"SS_MIN_SCORE": "101"},
        {"SS_FAIL_ON": "everything"},
        {"SS_TIMEOUT_MINUTES": "0"},
        {"SS_TIMEOUT_MINUTES": "99"},
        {"SS_API_URL": "http://evil.example.com/api"},
    ],
)
def test_input_validation(tmp_path: Path, fake_factory: Factory, env: dict[str, str]) -> None:
    f = fake_factory((202, _scan()), [(200, _scan())])
    code, log, _, _ = run(tmp_path, f, **env)
    assert code == 2
    assert "::error::SecureScope" in log
    assert f.posted == []
