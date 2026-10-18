from __future__ import annotations

import httpx

from app.scanner.checks import run_checks
from app.scanner.fetcher import FetchResult
from app.scanner.scoring import compute_score, count_by_severity
from app.schemas.scan import Finding, Severity


def make_result(
    headers: list[tuple[str, str]] | None = None,
    *,
    scheme: str = "https",
    started_scheme: str | None = None,
    body: bytes = b"<html></html>",
    off_origin: str | None = None,
) -> FetchResult:
    url = f"{scheme}://example.com/"
    return FetchResult(
        requested_url=f"{started_scheme or scheme}://example.com/",
        final_url=url,
        status_code=200,
        headers=httpx.Headers(headers or [("content-type", "text/html")]),
        body_sample=body,
        redirect_chain=[url],
        resolved_addresses=["93.184.216.34"],
        off_origin_redirect=off_origin,
        started_scheme=started_scheme or scheme,
        final_scheme=scheme,
        host="example.com",
    )


def ids(result: FetchResult) -> set[str]:
    findings, _ = run_checks(result)
    return {f.id for f in findings}


GOOD_HEADERS = [
    ("content-type", "text/html"),
    ("strict-transport-security", "max-age=31536000; includeSubDomains"),
    ("content-security-policy", "default-src 'self'"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "camera=()"),
]


def test_hardened_https_site_has_no_findings() -> None:
    findings, names = run_checks(make_result(GOOD_HEADERS))
    assert findings == []
    assert "hsts" in names and "cookie-attributes" in names


def test_missing_headers_are_reported_on_https() -> None:
    found = ids(make_result())
    assert {
        "SS-HDR-HSTS-001",
        "SS-HDR-CSP-001",
        "SS-HDR-XCTO-001",
        "SS-HDR-REF-001",
        "SS-HDR-PERM-001",
    } <= found


def test_hsts_is_not_reported_over_plain_http() -> None:
    found = ids(make_result(scheme="http"))
    assert "SS-HDR-HSTS-001" not in found
    assert "SS-TLS-001" in found  # unencrypted HTTP itself is the finding


def test_http_to_https_redirect_is_informational() -> None:
    findings, _ = run_checks(make_result(GOOD_HEADERS, scheme="https", started_scheme="http"))
    assert [f.id for f in findings] == ["SS-TLS-002"]
    assert findings[0].severity is Severity.INFO


def test_short_hsts_max_age() -> None:
    headers = [h for h in GOOD_HEADERS if h[0] != "strict-transport-security"]
    headers.append(("strict-transport-security", "max-age=300"))
    assert ids(make_result(headers)) == {"SS-HDR-HSTS-002"}


def test_csp_unsafe_inline_flagged() -> None:
    headers = [h for h in GOOD_HEADERS if h[0] != "content-security-policy"]
    headers.append(("content-security-policy", "default-src 'self'; script-src 'self' 'unsafe-inline'"))
    assert ids(make_result(headers)) == {"SS-HDR-CSP-002"}


def test_wrong_nosniff_value_flagged() -> None:
    headers = [h for h in GOOD_HEADERS if h[0] != "x-content-type-options"]
    headers.append(("x-content-type-options", "sniff-away"))
    assert ids(make_result(headers)) == {"SS-HDR-XCTO-001"}


def test_disclosure_headers() -> None:
    headers = [*GOOD_HEADERS, ("server", "Apache/2.4.41 (Ubuntu)"), ("x-powered-by", "Express")]
    assert ids(make_result(headers)) == {"SS-DISC-SRV-001", "SS-DISC-XPB-001"}
    assert ids(make_result([*GOOD_HEADERS, ("server", "cloudflare")])) == {"SS-DISC-SRV-002"}


def test_cookie_attributes_and_value_redaction() -> None:
    headers = [
        *GOOD_HEADERS,
        ("set-cookie", "sid=SUPERSECRETVALUE; Path=/"),
        ("set-cookie", "ok=1; Secure; HttpOnly; SameSite=Strict"),
    ]
    findings, _ = run_checks(make_result(headers))
    assert {f.id for f in findings} == {
        "SS-COOKIE-SECURE-001",
        "SS-COOKIE-HTTPONLY-001",
        "SS-COOKIE-SAMESITE-001",
    }
    blob = " ".join((f.evidence or "") for f in findings)
    assert "sid" in blob
    assert "SUPERSECRETVALUE" not in blob  # cookie values never leave the checker


def test_secure_flag_not_demanded_over_http() -> None:
    headers = [*GOOD_HEADERS, ("set-cookie", "a=1; HttpOnly; SameSite=Lax")]
    assert "SS-COOKIE-SECURE-001" not in ids(make_result(headers, scheme="http"))


def test_directory_listing_signature() -> None:
    body = b"<html><head><title>Index of /backup</title></head><body><h1>Index of /backup</h1></body>"
    assert "SS-DIR-001" in ids(make_result(GOOD_HEADERS, body=body))
    assert "SS-DIR-001" not in ids(make_result(GOOD_HEADERS, body=b"<html><p>The word index of things</p>"))


def test_compressed_or_binary_bodies_are_not_inspected() -> None:
    body = b"<title>Index of /x</title>"
    compressed = [*GOOD_HEADERS, ("content-encoding", "gzip")]
    assert "SS-DIR-001" not in ids(make_result(compressed, body=body))
    binary = [("content-type", "image/png"), *GOOD_HEADERS[1:]]
    assert "SS-DIR-001" not in ids(make_result(binary, body=body))


def test_off_origin_redirect_is_reported_not_followed() -> None:
    assert "SS-SCOPE-001" in ids(make_result(GOOD_HEADERS, off_origin="https://other.example"))


def test_every_finding_is_complete_and_ids_are_stable() -> None:
    headers = [
        ("server", "nginx/1.2.3"),
        ("x-powered-by", "PHP"),
        ("set-cookie", "a=b"),
    ]
    findings, _ = run_checks(make_result(headers, body=b"<title>Index of /</title>"))
    assert findings
    seen = set()
    for finding in findings:
        assert finding.id.startswith("SS-") and finding.id not in seen
        seen.add(finding.id)
        assert finding.title and finding.description and finding.remediation


def finding(severity: Severity, n: int = 1) -> list[Finding]:
    return [
        Finding(
            id=f"X-{severity}-{i}",
            title="t",
            severity=severity,
            category="c",
            description="d",
            remediation="r",
        )
        for i in range(n)
    ]


def test_scoring_bounds_and_grades() -> None:
    assert compute_score([]) == (100, "A")
    assert compute_score(finding(Severity.INFO, 10)) == (100, "A")
    assert compute_score(finding(Severity.LOW)) == (96, "A")
    assert compute_score(finding(Severity.MEDIUM, 2)) == (80, "B")
    assert compute_score(finding(Severity.HIGH) + finding(Severity.MEDIUM)) == (70, "C")
    assert compute_score(finding(Severity.HIGH, 2)) == (60, "D")
    assert compute_score(finding(Severity.CRITICAL, 3)) == (0, "F")


def test_count_by_severity_includes_zeroes() -> None:
    counts = count_by_severity(finding(Severity.HIGH, 2) + finding(Severity.LOW))
    assert counts == {"critical": 0, "high": 2, "medium": 0, "low": 1, "info": 0}


def test_missing_header_evidence_names_what_was_observed() -> None:
    result = make_result([("content-type", "text/html"), ("x-content-type-options", "nosniff")])
    findings, _ = run_checks(result)
    hsts = next(f for f in findings if f.id == "SS-HDR-HSTS-001")
    assert hsts.evidence is not None
    assert "https://example.com/" in hsts.evidence
    assert "HTTP 200" in hsts.evidence
    assert "x-content-type-options: nosniff" in hsts.evidence


def test_missing_header_evidence_when_no_security_headers() -> None:
    findings, _ = run_checks(make_result())
    csp = next(f for f in findings if f.id == "SS-HDR-CSP-001")
    assert csp.evidence is not None and "none of the common security headers" in csp.evidence
