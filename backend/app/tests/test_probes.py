"""Fixed-path probes: exposed .git / .env detection, security.txt, false-positive resistance, safety."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.scanner.checks import PROBE_PATHS, assess
from app.scanner.fetcher import FetchResult, ProbeResponse, fetch_probe
from app.tests.test_checks_and_scoring import make_result

SPA = b"<!doctype html><html><body><div id=root></div></body></html>"


def resp(path: str, status: int | None, body: bytes = b"", kind: str = "text/plain", error: str | None = None):  # type: ignore[no-untyped-def]
    return ProbeResponse(path, status=status, content_type=kind, body_sample=body, error=error)


def probes(**over: ProbeResponse) -> dict[str, ProbeResponse]:
    base = {p: resp(p, 404) for p in PROBE_PATHS}
    base.update({p.replace("__", "/"): r for p, r in over.items()})
    return base


def ids(result_probes: dict[str, ProbeResponse]) -> set[str]:
    return {f.id for f in assess(make_result(), None, result_probes).findings}


def test_git_head_detected_without_storing_content() -> None:
    p = probes()
    p["/.git/HEAD"] = resp("/.git/HEAD", 200, b"ref: refs/heads/main\n")
    found = assess(make_result(), None, p).findings
    git = next(f for f in found if f.id == "SS-EXPOSE-GIT-001")
    assert "refs/heads/main" not in (git.evidence or "")


def test_env_file_detected_but_values_not_stored() -> None:
    p = probes()
    p["/.env"] = resp("/.env", 200, b"DB_PASSWORD=hunter2\nAPI_KEY=abc\n")
    found = assess(make_result(), None, p).findings
    env = next(f for f in found if f.id == "SS-EXPOSE-ENV-001")
    assert "hunter2" not in (env.evidence or "") and "DB_PASSWORD" not in (env.evidence or "")


def test_spa_catch_all_is_not_a_false_positive() -> None:
    p = probes()
    for path in PROBE_PATHS:
        p[path] = resp(path, 200, SPA, kind="text/html")
    found = ids(p)
    assert not {"SS-EXPOSE-GIT-001", "SS-EXPOSE-ENV-001"} & found
    assert "SS-DISC-SEC-001" in found  # the HTML is not a security.txt


def test_plain_text_that_is_not_a_git_or_env_file_is_ignored() -> None:
    p = probes()
    p["/.git/HEAD"] = resp("/.git/HEAD", 200, b"hello world")
    p["/.env"] = resp("/.env", 200, b"just one line = here")
    assert not {"SS-EXPOSE-GIT-001", "SS-EXPOSE-ENV-001"} & ids(p)


def test_valid_security_txt_clears_the_note() -> None:
    p = probes()
    p["/.well-known/security.txt"] = resp("/.well-known/security.txt", 200, b"Contact: mailto:a@b.example\n")
    assert "SS-DISC-SEC-001" not in ids(p)


def test_server_error_skips_check_instead_of_passing_it() -> None:
    p = probes()
    p["/.git/HEAD"] = resp("/.git/HEAD", 503)
    a = assess(make_result(), None, p)
    assert "exposed-files" not in a.checks_run
    assert any(s.name == "exposed-files" for s in a.checks_skipped)
    assert "SS-EXPOSE-" in a.unverified_prefixes[0] or any(x.startswith("SS-EXPOSE-") for x in a.unverified_prefixes)


def test_transport_error_skips_check() -> None:
    p = probes()
    p["/.well-known/security.txt"] = resp("/.well-known/security.txt", None, error="The request timed out.")
    a = assess(make_result(), None, p)
    assert any(s.name == "security-txt" for s in a.checks_skipped)
    assert "SS-DISC-SEC-001" not in {f.id for f in a.findings}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        routes = {
            "/.git/HEAD": (200, b"ref: refs/heads/main\n"),
            "/.env": (302, b""),
        }
        status, body = routes.get(self.path, (404, b"nope"))
        self.send_response(status)
        if status == 302:
            self.send_header("Location", "/login")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server() -> Iterator[int]:
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield int(s.server_address[1])
    s.shutdown()


def base_for(port: int) -> FetchResult:
    return FetchResult(
        requested_url=f"http://127.0.0.1:{port}/",
        final_url=f"http://127.0.0.1:{port}/",
        status_code=200,
        headers=httpx.Headers(),
        body_sample=b"",
        host="127.0.0.1",
        port=port,
        started_scheme="http",
        final_scheme="http",
    )


def test_fetch_probe_reads_file_and_does_not_follow_redirects(make_settings, server: int) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True, request_timeout_seconds=2.0)
    base = base_for(server)
    git = asyncio.run(fetch_probe(base, "/.git/HEAD", settings))
    assert git.status == 200 and git.body_sample.startswith(b"ref: refs/")
    env = asyncio.run(fetch_probe(base, "/.env", settings))
    assert env.status == 302 and env.body_sample == b""


def test_fetch_probe_refuses_private_targets_by_default(make_settings, server: int) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=False)
    out = asyncio.run(fetch_probe(base_for(server), "/.git/HEAD", settings))
    assert out.status is None and out.error


def test_fetch_probe_rejects_non_fixed_paths(make_settings) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(allow_private_targets=True)
    for bad in ("x", "/a?b=1", "/a#b", "/a b"):
        with pytest.raises(ValueError):
            asyncio.run(fetch_probe(base_for(1), bad, settings))


def test_skipped_checks_appear_in_reports(db_url: str) -> None:
    from app.reporting import reports
    from app.schemas.scan import SkippedCheck
    from app.tests.test_db_and_reports import completed_detail

    detail = completed_detail(db_url)
    assert detail.metadata is not None
    detail = detail.model_copy(
        update={
            "metadata": detail.metadata.model_copy(
                update={"checks_skipped": [SkippedCheck(name="exposed-files", reason="No usable answer.")]}
            )
        }
    )
    assert "Not checked: No exposed .git directory or .env file" in reports.to_markdown(detail)
    assert "Not checked" in reports.to_html(detail)
    assert reports.to_pdf(detail)[:4] == b"%PDF"


def test_missing_security_txt_is_not_listed_as_passed(db_url: str) -> None:
    from app.reporting import reports
    from app.tests.test_db_and_reports import completed_detail

    detail = completed_detail(db_url)
    assert detail.metadata is not None
    a = assess(make_result(), None, probes())
    detail = detail.model_copy(
        update={
            "findings": a.findings,
            "metadata": detail.metadata.model_copy(update={"checks_run": a.checks_run}),
        }
    )
    passed = reports.passed_checks(detail)
    assert "A security.txt contact file is published" not in passed
    assert "No exposed .git directory or .env file" in passed
