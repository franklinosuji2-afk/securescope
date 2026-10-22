"""Scan accuracy: whole-scan scenarios with a known right answer.

Each scenario describes a site the way the scanner sees it (page response, the three fixed probe paths and
the TLS observation) and states exactly which findings, severities, score and grade a correct scan produces.
The tests fail on a missed finding, an extra one, a changed severity or a changed score, so a change to a
check cannot quietly make reports less accurate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.scanner.checks import PROBE_PATHS, assess, check_tls_certificate
from app.scanner.fetcher import FetchResult, ProbeResponse
from app.scanner.scoring import compute_score
from app.scanner.tls import TlsObservation
from app.schemas.scan import Severity

NOW = datetime.now(UTC)
M, L, H, I = Severity.MEDIUM, Severity.LOW, Severity.HIGH, Severity.INFO  # noqa: E741

GOOD_HEADERS = [
    ("content-type", "text/html; charset=utf-8"),
    ("strict-transport-security", "max-age=31536000; includeSubDomains"),
    ("content-security-policy", "default-src 'self'"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "camera=(), microphone=()"),
]
SECURITY_TXT = b"Contact: mailto:security@example.com\nExpires: 2027-12-31T23:59:59Z\n"


def probe(
    path: str, status: int | None = 404, body: bytes = b"", content_type: str = "text/plain"
) -> ProbeResponse:
    if status is None:
        return ProbeResponse(path=path, error="timeout")
    return ProbeResponse(path=path, status=status, content_type=content_type, body_sample=body)


def clean_probes(**overrides: ProbeResponse) -> dict[str, ProbeResponse]:
    probes = {
        "/.well-known/security.txt": probe("/.well-known/security.txt", 200, SECURITY_TXT),
        "/.git/HEAD": probe("/.git/HEAD", 404),
        "/.env": probe("/.env", 404),
    }
    probes.update(overrides)
    return probes


def good_tls(days: int = 80) -> TlsObservation:
    return TlsObservation(
        outcome="ok",
        protocol="TLSv1.3",
        cipher="TLS_AES_256_GCM_SHA384",
        not_before=NOW - timedelta(days=10),
        not_after=NOW + timedelta(days=days),
        issuer="Example CA",
        subject="example.com",
    )


def page(
    headers: list[tuple[str, str]],
    *,
    scheme: str = "https",
    started: str | None = None,
    body: bytes = b"<html><body>Welcome</body></html>",
    off_origin: str | None = None,
) -> FetchResult:
    started = started or scheme
    final = f"{scheme}://example.com/"
    return FetchResult(
        requested_url=f"{started}://example.com/",
        final_url=final,
        status_code=200,
        headers=httpx.Headers(headers),
        body_sample=body,
        redirect_chain=[final],
        resolved_addresses=["93.184.216.34"],
        off_origin_redirect=off_origin,
        started_scheme=started,
        final_scheme=scheme,
        host="example.com",
    )


@dataclass
class Scenario:
    name: str
    result: FetchResult
    probes: dict[str, ProbeResponse] | None
    tls: TlsObservation | None
    findings: dict[str, Severity]
    score: int
    grade: str
    skipped: set[str] = field(default_factory=set)


def without(*names: str) -> list[tuple[str, str]]:
    return [h for h in GOOD_HEADERS if h[0] not in names]


SCENARIOS = [
    Scenario(
        "hardened HTTPS site",
        page(GOOD_HEADERS),
        clean_probes(),
        good_tls(),
        {},
        100,
        "A",
    ),
    Scenario(
        "HTTPS site with no security headers and no security.txt",
        page([("content-type", "text/html")]),
        clean_probes(**{"/.well-known/security.txt": probe("/.well-known/security.txt", 404)}),
        good_tls(),
        {
            "SS-HDR-HSTS-001": M,
            "SS-HDR-CSP-001": M,
            "SS-HDR-XCTO-001": L,
            "SS-HDR-REF-001": L,
            "SS-HDR-PERM-001": I,
            "SS-DISC-SEC-001": I,
        },
        100 - 10 - 10 - 4 - 4,
        "C",
    ),
    Scenario(
        "plain HTTP site",
        page(without("strict-transport-security"), scheme="http"),
        clean_probes(),
        None,
        {"SS-TLS-001": H},
        80,
        "B",
        {"tls-certificate"},
    ),
    Scenario(
        "HTTP address that redirects to a hardened HTTPS site",
        page(GOOD_HEADERS, started="http"),
        clean_probes(),
        good_tls(),
        {"SS-TLS-002": I},
        100,
        "A",
    ),
    Scenario(
        "short HSTS lifetime and unsafe-inline script policy",
        page(
            [
                *without("strict-transport-security", "content-security-policy"),
                ("strict-transport-security", "max-age=300"),
                ("content-security-policy", "default-src 'self'; script-src 'self' 'unsafe-inline'"),
            ]
        ),
        clean_probes(),
        good_tls(),
        {"SS-HDR-HSTS-002": L, "SS-HDR-CSP-002": L},
        92,
        "A",
    ),
    Scenario(
        "server and framework announce their versions",
        page([*GOOD_HEADERS, ("server", "nginx/1.18.0"), ("x-powered-by", "PHP/7.4")]),
        clean_probes(),
        good_tls(),
        {"SS-DISC-SRV-001": L, "SS-DISC-XPB-001": L},
        92,
        "A",
    ),
    Scenario(
        "server names itself without a version",
        page([*GOOD_HEADERS, ("server", "cloudflare")]),
        clean_probes(),
        good_tls(),
        {"SS-DISC-SRV-002": I},
        100,
        "A",
    ),
    Scenario(
        "session cookie without any protection",
        page([*GOOD_HEADERS, ("set-cookie", "session=abc123; Path=/")]),
        clean_probes(),
        good_tls(),
        {"SS-COOKIE-SECURE-001": M, "SS-COOKIE-HTTPONLY-001": L, "SS-COOKIE-SAMESITE-001": L},
        82,
        "B",
    ),
    Scenario(
        "well-protected cookie",
        page([*GOOD_HEADERS, ("set-cookie", "session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax")]),
        clean_probes(),
        good_tls(),
        {},
        100,
        "A",
    ),
    Scenario(
        "exposed .env file and git metadata",
        page(GOOD_HEADERS),
        clean_probes(
            **{
                "/.env": probe("/.env", 200, b"DB_PASSWORD=x\nAPI_KEY=y\n"),
                "/.git/HEAD": probe("/.git/HEAD", 200, b"ref: refs/heads/main\n"),
            }
        ),
        good_tls(),
        {"SS-EXPOSE-ENV-001": H, "SS-EXPOSE-GIT-001": H},
        60,
        "D",
    ),
    Scenario(
        "single-page app that answers every path with its home page",
        page(GOOD_HEADERS),
        clean_probes(
            **{
                "/.well-known/security.txt": probe(
                    "/.well-known/security.txt", 200, b"<!doctype html><html></html>", "text/html"
                ),
                "/.git/HEAD": probe("/.git/HEAD", 200, b"<!doctype html><html></html>", "text/html"),
                "/.env": probe("/.env", 200, b"<!doctype html><html>KEY=VALUE\nA=B</html>", "text/html"),
            }
        ),
        good_tls(),
        {"SS-DISC-SEC-001": I},  # no valid security.txt, but no false claim of exposed files
        100,
        "A",
    ),
    Scenario(
        "a .env path with only one KEY=VALUE-looking line is not reported",
        page(GOOD_HEADERS),
        clean_probes(**{"/.env": probe("/.env", 200, b"Welcome=home\nnothing else here\n")}),
        good_tls(),
        {},
        100,
        "A",
    ),
    Scenario(
        "directory listing",
        page(
            GOOD_HEADERS,
            body=b"<html><head><title>Index of /backup</title></head><body><h1>Index of /backup</h1>",
        ),
        clean_probes(),
        good_tls(),
        {"SS-DIR-001": M},
        90,
        "A",
    ),
    Scenario(
        "redirect to a different site is reported, not followed",
        page(GOOD_HEADERS, off_origin="https://other.example/"),
        clean_probes(),
        good_tls(),
        {"SS-SCOPE-001": I},
        100,
        "A",
    ),
    Scenario(
        "certificate expiring in 20 days",
        page(GOOD_HEADERS),
        clean_probes(),
        good_tls(days=20),
        {"SS-TLS-CERT-001": M},
        90,
        "A",
    ),
    Scenario(
        "certificate expiring in 5 days",
        page(GOOD_HEADERS),
        clean_probes(),
        good_tls(days=5),
        {"SS-TLS-CERT-001": H},
        80,
        "B",
    ),
    Scenario(
        "certificate that has expired",
        page(GOOD_HEADERS),
        clean_probes(),
        TlsObservation(
            outcome="verification_failed",
            failure_kind="expired",
            detail="certificate has expired",
            not_before=NOW - timedelta(days=400),
            not_after=NOW - timedelta(days=2),
        ),
        {"SS-TLS-CERT-002": H},
        80,
        "B",
    ),
    Scenario(
        "probes that fail are not checked and never reported as passed",
        page(GOOD_HEADERS),
        {
            "/.well-known/security.txt": probe("/.well-known/security.txt", None),
            "/.git/HEAD": probe("/.git/HEAD", 503),
            "/.env": probe("/.env", 429),
        },
        good_tls(),
        {},
        100,
        "A",
        {"exposed-files", "security-txt"},
    ),
    Scenario(
        "TLS check that could not run is skipped, not passed",
        page(GOOD_HEADERS),
        clean_probes(),
        TlsObservation(outcome="error", detail="timed out"),
        {},
        100,
        "A",
        {"tls-certificate"},
    ),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scan_reports_exactly_the_expected_findings(scenario: Scenario) -> None:
    assessment = assess(scenario.result, scenario.tls, scenario.probes)
    reported = {f.id: f.severity for f in assessment.findings}
    assert reported == scenario.findings
    assert len(assessment.findings) == len({f.id for f in assessment.findings}), "duplicate finding ids"
    assert compute_score(assessment.findings) == (scenario.score, scenario.grade)
    assert {s.name for s in assessment.checks_skipped} == scenario.skipped
    # A check that did not run must not appear as run, and nothing is both run and skipped.
    assert not set(assessment.checks_run) & {s.name for s in assessment.checks_skipped}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_every_reported_finding_is_complete_and_evidenced(scenario: Scenario) -> None:
    for finding in assess(scenario.result, scenario.tls, scenario.probes).findings:
        assert finding.title and finding.description and finding.remediation, finding.id
        assert finding.evidence, f"{finding.id} has no evidence"
        assert finding.category


def test_skipped_checks_protect_earlier_findings_from_being_marked_resolved() -> None:
    scenario = next(s for s in SCENARIOS if s.name.startswith("probes that fail"))
    assessment = assess(scenario.result, scenario.tls, scenario.probes)
    assert set(assessment.unverified_prefixes) == {"SS-EXPOSE-", "SS-DISC-SEC-"}


def test_scanning_the_same_site_twice_gives_the_same_answer() -> None:
    first = assess(SCENARIOS[1].result, good_tls(), SCENARIOS[1].probes)
    second = assess(SCENARIOS[1].result, good_tls(), SCENARIOS[1].probes)
    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]


def test_header_names_and_values_are_matched_case_insensitively() -> None:
    shouting = [(n.upper(), v.upper() if n == "x-content-type-options" else v) for n, v in GOOD_HEADERS]
    assert assess(page(shouting), good_tls(), clean_probes()).findings == []


def test_secrets_in_cookies_and_files_never_reach_the_report() -> None:
    result = page([*GOOD_HEADERS, ("set-cookie", "token=TOPSECRETVALUE")])
    probes = clean_probes(
        **{"/.env": probe("/.env", 200, b"DB_PASSWORD=hunter2hunter2\nAPI_KEY=abcdef123456\n")}
    )
    blob = " ".join(
        f"{f.title} {f.description} {f.evidence} {f.remediation}"
        for f in assess(result, good_tls(), probes).findings
    )
    for secret in ("TOPSECRETVALUE", "hunter2hunter2", "abcdef123456"):
        assert secret not in blob


@pytest.mark.parametrize("kind", ["expired", "not_yet_valid", "hostname_mismatch", "untrusted", "other"])
def test_each_certificate_failure_has_its_own_finding_id(kind: str) -> None:
    tls = TlsObservation(outcome="verification_failed", failure_kind=kind, detail="x")  # type: ignore[arg-type]
    ids = {kind: check_tls_certificate(page(GOOD_HEADERS), tls)[0].id}
    assert ids[kind].startswith("SS-TLS-CERT-")


def test_certificate_failure_ids_are_unique() -> None:
    kinds = ["expired", "not_yet_valid", "hostname_mismatch", "untrusted", "other"]
    seen = [
        check_tls_certificate(
            page(GOOD_HEADERS),
            TlsObservation(outcome="verification_failed", failure_kind=k, detail="x"),  # type: ignore[arg-type]
        )[0].id
        for k in kinds
    ]
    assert len(seen) == len(set(seen)), seen


def test_probe_paths_are_the_documented_fixed_three() -> None:
    assert PROBE_PATHS == ("/.well-known/security.txt", "/.git/HEAD", "/.env")
