"""TLS connection assessment: certificate validity, host name, trust, protocol, failures, resolving."""

from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.repositories.scans import ScanRepository
from app.scanner.checks import assess
from app.scanner.tls import TlsObservation, probe_tls
from app.schemas.scan import FindingStatus, Severity, TargetMetadata
from app.tests.test_checks_and_scoring import make_result
from app.tests.test_db_and_reports import make_org, make_repo
from app.tests.test_finding_lifecycle import finding, status_of
from app.tests.tls_certs import OPENSSL, make_cert

pytestmark = pytest.mark.skipif(
    OPENSSL is None, reason="the openssl command is needed to make test certificates"
)

HOST = "tls.test"


@contextmanager
def tls_server(cert: Path, key: Path) -> Iterator[int]:
    """A local TLS server that completes handshakes using the given certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    stop = threading.Event()

    def serve() -> None:
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except (TimeoutError, OSError):
                continue
            try:
                context.wrap_socket(connection, server_side=True).close()
            except (ssl.SSLError, OSError):
                connection.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield int(listener.getsockname()[1])
    finally:
        stop.set()
        thread.join(timeout=2)
        listener.close()


def trusting(cert: Path) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(cert))


def test_a_valid_certificate_is_verified_and_described(tmp_path: Path) -> None:
    cert, key = make_cert(tmp_path, "ok", HOST, days_from=-1, days_to=90)
    with tls_server(cert, key) as port:
        obs = probe_tls(HOST, "127.0.0.1", port, 3, trusting(cert))
    assert obs.outcome == "ok"
    assert obs.protocol in ("TLSv1.2", "TLSv1.3")
    assert obs.cipher
    assert obs.subject == HOST
    assert obs.days_remaining() in (89, 90)


def test_an_expired_certificate_is_classified_not_ignored(tmp_path: Path) -> None:
    cert, key = make_cert(tmp_path, "old", HOST, days_from=-400, days_to=-35)
    with tls_server(cert, key) as port:
        obs = probe_tls(HOST, "127.0.0.1", port, 3, trusting(cert))
    assert obs.outcome == "verification_failed"
    assert obs.failure_kind == "expired"


def test_a_certificate_for_another_name_is_a_hostname_mismatch(tmp_path: Path) -> None:
    cert, key = make_cert(tmp_path, "other", "someone-else.test", days_from=-1, days_to=90)
    with tls_server(cert, key) as port:
        obs = probe_tls(HOST, "127.0.0.1", port, 3, trusting(cert))
    assert obs.outcome == "verification_failed"
    assert obs.failure_kind == "hostname_mismatch"


def test_a_self_signed_certificate_is_untrusted_with_the_default_trust_store(tmp_path: Path) -> None:
    cert, key = make_cert(tmp_path, "self", HOST, days_from=-1, days_to=90)
    with tls_server(cert, key) as port:
        obs = probe_tls(HOST, "127.0.0.1", port, 3)  # production context: nothing extra is trusted
    assert obs.outcome == "verification_failed"
    assert obs.failure_kind == "untrusted"


def test_a_closed_port_and_a_silent_server_are_connection_failures_not_findings() -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    assert probe_tls(HOST, "127.0.0.1", port, 1).outcome == "unreachable"

    silent = socket.socket()
    silent.bind(("127.0.0.1", 0))
    silent.listen(1)
    try:
        obs = probe_tls(HOST, "127.0.0.1", silent.getsockname()[1], 0.3)
    finally:
        silent.close()
    assert obs.outcome == "unreachable"
    assert "timed out" in (obs.detail or "")


def test_a_server_that_does_not_speak_tls_is_a_handshake_error() -> None:
    plain = socket.socket()
    plain.bind(("127.0.0.1", 0))
    plain.listen(1)

    def answer() -> None:
        connection, _ = plain.accept()
        connection.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        connection.close()

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    try:
        obs = probe_tls(HOST, "127.0.0.1", plain.getsockname()[1], 2)
    finally:
        thread.join(timeout=2)
        plain.close()
    assert obs.outcome == "error"


# --- findings ----------------------------------------------------------------------------


def observation(tmp_path: Path, days_to: int, name: str = "x") -> TlsObservation:
    cert, key = make_cert(tmp_path, name, HOST, days_from=-1, days_to=days_to)
    with tls_server(cert, key) as port:
        return probe_tls(HOST, "127.0.0.1", port, 3, trusting(cert))


def test_expiry_findings_scale_with_the_time_left(tmp_path: Path) -> None:
    soon = assess(make_result(), observation(tmp_path / "a", 10))
    assert [(f.id, f.severity) for f in soon.findings if f.id.startswith("SS-TLS-CERT")] == [
        ("SS-TLS-CERT-001", Severity.HIGH)
    ]
    later = assess(make_result(), observation(tmp_path / "b", 25))
    assert [(f.id, f.severity) for f in later.findings if f.id.startswith("SS-TLS-CERT")] == [
        ("SS-TLS-CERT-001", Severity.MEDIUM)
    ]
    healthy = assess(make_result(), observation(tmp_path / "c", 90))
    assert not [f for f in healthy.findings if f.id.startswith("SS-TLS-CERT")]
    assert "tls-certificate" in healthy.checks_run
    assert healthy.tls is not None and healthy.tls.verified and healthy.tls.protocol


def test_verification_failures_become_high_findings_with_evidence(tmp_path: Path) -> None:
    cert, key = make_cert(tmp_path, "old", HOST, days_from=-400, days_to=-35)
    with tls_server(cert, key) as port:
        expired = probe_tls(HOST, "127.0.0.1", port, 3, trusting(cert))
    found = [f for f in assess(make_result(), expired).findings if f.id.startswith("SS-TLS-CERT")]
    assert [f.id for f in found] == ["SS-TLS-CERT-002"]
    assert found[0].severity == Severity.HIGH and "expired" in (found[0].evidence or "")


def test_a_check_that_could_not_run_is_reported_as_skipped_never_as_passed() -> None:
    down = TlsObservation(outcome="unreachable", detail="The TLS connection timed out.")
    result = assess(make_result(), down)
    assert "tls-certificate" not in result.checks_run
    assert [(s.name, s.reason) for s in result.checks_skipped] == [
        ("tls-certificate", "The TLS connection timed out.")
    ]
    assert result.unverified_prefixes == ("SS-TLS-CERT-",)
    http_only = assess(make_result(scheme="http"), None)
    assert http_only.checks_skipped and "HTTP" in http_only.checks_skipped[0].reason
    assert "tls-certificate" not in http_only.checks_run


def test_an_unrun_check_does_not_resolve_its_earlier_findings(db_url: str) -> None:
    repo: ScanRepository = make_repo(db_url)
    org, user = make_org(db_url)
    first = repo.create_scan(org, user, "https://a.example/", "a.example")
    meta = TargetMetadata(requested_url="https://a.example/", host="a.example")
    repo.complete_scan(first, [finding("SS-TLS-CERT-001"), finding("SS-HDR-CSP-001")], 80, "B", meta)

    second = repo.create_scan(org, user, "https://a.example/", "a.example")
    repo.complete_scan(second, [], 100, "A", meta, ("SS-TLS-CERT-",))
    assert status_of(repo, first, org, "SS-TLS-CERT-001").status == FindingStatus.OPEN
    assert status_of(repo, first, org, "SS-HDR-CSP-001").status == FindingStatus.RESOLVED

    third = repo.create_scan(org, user, "https://a.example/", "a.example")
    repo.complete_scan(third, [], 100, "A", meta)  # the check ran this time and found nothing
    assert status_of(repo, first, org, "SS-TLS-CERT-001").status == FindingStatus.RESOLVED
