"""The wider passive checks: page content, cross-origin headers, robots.txt and sitemap.xml, and DNS and email."""

from __future__ import annotations

import asyncio

import pytest

from app.scanner.checks import assess
from app.scanner.dns_checks import (
    DnsAnswer,
    DnsObservation,
    check_caa,
    check_dmarc,
    check_dnssec,
    check_spf,
    eligible_domain,
    observe_dns,
)
from app.scanner.page_checks import (
    check_cors,
    check_mixed_content,
    check_robots_and_sitemap,
    check_subresource_integrity,
)
from app.scanner.scoring import compute_score
from app.schemas.scan import Confidence, Severity
from app.tests.test_scan_accuracy import GOOD_HEADERS, clean_probes, good_tls, page, probe


def html(markup: str, headers: list[tuple[str, str]] | None = None, scheme: str = "https"):  # type: ignore[no-untyped-def]
    return page(headers or GOOD_HEADERS, scheme=scheme, body=markup.encode())


def ids(findings) -> list[str]:  # type: ignore[no-untyped-def]
    return [f.id for f in findings]


# --- mixed content --------------------------------------------------------------------------------------


def test_active_http_resources_on_an_https_page_are_a_medium_finding() -> None:
    result = html(
        '<script src="http://cdn.example.net/a.js?token=SECRET"></script>'
        '<form action="http://example.com/post"></form><img src="https://example.com/ok.png">'
    )
    found = check_mixed_content(result)
    assert ids(found) == ["SS-MIX-001"]
    assert found[0].severity == Severity.MEDIUM
    assert "SECRET" not in (found[0].evidence or "")  # query strings can carry tokens and are not repeated
    assert "2 resource(s)" in (found[0].evidence or "")


def test_passive_http_resources_are_a_low_finding_and_https_ones_are_fine() -> None:
    found = check_mixed_content(
        html('<img src="http://example.com/a.png"><video src="http://x.example/v.mp4">')
    )
    assert ids(found) == ["SS-MIX-002"] and found[0].severity == Severity.LOW
    assert (
        check_mixed_content(html('<img src="https://example.com/a.png"><a href="http://other.example">x</a>'))
        == []
    )


def test_mixed_content_is_not_reported_for_plain_http_pages_or_non_html() -> None:
    assert check_mixed_content(html('<script src="http://x.example/a.js"></script>', scheme="http")) == []
    json_page = page([("content-type", "application/json")], body=b'<script src="http://x.example/a.js">')
    assert check_mixed_content(json_page) == []


def test_malformed_markup_never_breaks_a_scan() -> None:
    assert check_mixed_content(html("<script src=<<>>>\x00 <img src='http://a.example/x.png")) is not None


# --- subresource integrity ------------------------------------------------------------------------------


def test_third_party_scripts_without_integrity_are_flagged_and_pinned_ones_are_not() -> None:
    result = html(
        '<script src="https://cdn.example.net/lib.js"></script>'
        '<script src="https://cdn.example.net/pinned.js" integrity="sha384-abc" crossorigin="anonymous"></script>'
        '<link rel="stylesheet" href="//fonts.example.org/a.css">'
        '<script src="/local.js"></script><script src="https://www.example.com/same-site.js"></script>'
        '<link rel="icon" href="https://cdn.example.net/icon.png">'
    )
    found = check_subresource_integrity(result)
    assert ids(found) == ["SS-SRI-001"] and found[0].severity == Severity.LOW
    assert "2 script or stylesheet" in (found[0].evidence or "")
    assert "pinned.js" not in (found[0].evidence or "") and "same-site" not in (found[0].evidence or "")


def test_a_page_with_only_its_own_scripts_has_no_sri_finding() -> None:
    assert check_subresource_integrity(html('<script src="/a.js"></script><script>inline()</script>')) == []


# --- CORS -----------------------------------------------------------------------------------------------


def test_wildcard_with_credentials_and_null_origin_are_flagged() -> None:
    wild = page(
        [*GOOD_HEADERS, ("access-control-allow-origin", "*"), ("access-control-allow-credentials", "true")]
    )
    assert ids(check_cors(wild)) == ["SS-CORS-001"]
    null = page([*GOOD_HEADERS, ("access-control-allow-origin", "null")])
    assert ids(check_cors(null)) == ["SS-CORS-002"]


def test_a_named_origin_or_a_plain_wildcard_is_not_flagged() -> None:
    assert check_cors(page([*GOOD_HEADERS, ("access-control-allow-origin", "https://app.example.com")])) == []
    assert check_cors(page([*GOOD_HEADERS, ("access-control-allow-origin", "*")])) == []
    assert check_cors(page(GOOD_HEADERS)) == []


# --- robots.txt and sitemap.xml -------------------------------------------------------------------------


def test_sensitive_looking_paths_in_robots_and_sitemap_are_informational() -> None:
    probes = clean_probes(
        **{
            "/robots.txt": probe(
                "/robots.txt",
                200,
                b"User-agent: *\nDisallow: /admin/\nDisallow: /backup-2024\nDisallow: /search\n",
            ),
            "/sitemap.xml": probe(
                "/sitemap.xml",
                200,
                b"<urlset><url><loc>https://example.com/</loc></url><url><loc>https://example.com/staging/login</loc></url>"
                b"<url><loc>https://other.example/admin</loc></url></urlset>",
                "application/xml",
            ),
        }
    )
    found = check_robots_and_sitemap(page(GOOD_HEADERS), probes)
    assert ids(found) == ["SS-DISC-ROBOTS-001", "SS-DISC-SITEMAP-001"]
    assert all(f.severity == Severity.INFO for f in found)
    assert "/admin/" in (found[0].evidence or "") and "/search" not in (found[0].evidence or "")
    assert "/staging/login" in (found[1].evidence or "") and "other.example" not in (found[1].evidence or "")


def test_a_single_page_app_answering_every_path_with_html_is_not_misread() -> None:
    spa = b"<html><body>admin backup staging</body></html>"
    probes = clean_probes(
        **{
            "/robots.txt": probe("/robots.txt", 200, spa, "text/html"),
            "/sitemap.xml": probe("/sitemap.xml", 200, spa, "text/html"),
        }
    )
    assert check_robots_and_sitemap(page(GOOD_HEADERS), probes) == []


def test_robots_findings_are_marked_as_heuristic_in_a_full_assessment() -> None:
    probes = clean_probes(**{"/robots.txt": probe("/robots.txt", 200, b"Disallow: /admin\n")})
    assessment = assess(page(GOOD_HEADERS), good_tls(), probes)
    robots = next(f for f in assessment.findings if f.id == "SS-DISC-ROBOTS-001")
    assert robots.confidence == Confidence.MEDIUM
    assert "robots-sitemap" in assessment.checks_run


# --- DNS and email --------------------------------------------------------------------------------------

NONE = DnsAnswer("none")


def dns(*, txt=NONE, dmarc=NONE, caa=NONE, ds=NONE, domain="example.com") -> DnsObservation:  # type: ignore[no-untyped-def]
    return DnsObservation(domain, txt, dmarc, caa, ds)


def ok(*records: str) -> DnsAnswer:
    return DnsAnswer("ok", records)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("example.com", "example.com"),
        ("www.example.com", "example.com"),
        ("EXAMPLE.com.", "example.com"),
        ("example.co.uk", "example.co.uk"),
        ("shop.example.com", None),
        ("shop.example.co.uk", None),
        ("cfo-dev.pages.dev", None),
        ("localhost", None),
        ("127.0.0.1", None),
        ("[::1]", None),
    ],
)
def test_dns_checks_run_only_for_a_main_domain(host: str, expected: str | None) -> None:
    assert eligible_domain(host) == expected


def test_a_missing_spf_record_and_a_permissive_one_are_reported() -> None:
    missing = check_spf(dns(txt=ok("google-site-verification=abc")))
    assert ids(missing) == ["SS-DNS-SPF-001"] and missing[0].severity == Severity.LOW
    assert "google-site-verification" not in (missing[0].evidence or "")  # unrelated records are never echoed
    assert ids(check_spf(dns(txt=NONE))) == ["SS-DNS-SPF-001"]
    for ending in ("+all", "?all", "all"):
        found = check_spf(dns(txt=ok(f"v=spf1 include:_spf.example.net {ending}")))
        assert ids(found) == ["SS-DNS-SPF-002"] and found[0].severity == Severity.MEDIUM
    for fine in ("v=spf1 include:_spf.example.net ~all", "v=spf1 -all", "v=spf1 redirect=_spf.example.net"):
        assert check_spf(dns(txt=ok(fine))) == []
    assert ids(check_spf(dns(txt=ok("v=spf1 -all", "v=spf1 ~all")))) == ["SS-DNS-SPF-003"]


def test_dmarc_missing_and_monitor_only_policies() -> None:
    assert ids(check_dmarc(dns(dmarc=NONE))) == ["SS-DNS-DMARC-001"]
    monitor = check_dmarc(dns(dmarc=ok("v=DMARC1; p=none; rua=mailto:r@example.com")))
    assert ids(monitor) == ["SS-DNS-DMARC-002"] and monitor[0].severity == Severity.INFO
    assert check_dmarc(dns(dmarc=ok("v=DMARC1; p=reject"))) == []
    assert check_dmarc(dns(dmarc=ok("v=DMARC1; p=quarantine; pct=50"))) == []


def test_caa_and_dnssec_are_informational_and_only_when_clearly_absent() -> None:
    assert ids(check_caa(dns(caa=NONE))) == ["SS-DNS-CAA-001"]
    assert check_caa(dns(caa=ok('0 issue "letsencrypt.org"'))) == []
    assert ids(check_dnssec(dns(ds=NONE))) == ["SS-DNS-DNSSEC-001"]
    assert check_dnssec(dns(ds=ok("12345 13 2 ABCDEF"))) == []
    assert all(f.severity == Severity.INFO for f in check_caa(dns()) + check_dnssec(dns()))


def test_a_failed_lookup_is_skipped_and_never_reported_as_missing() -> None:
    broken = dns(
        txt=DnsAnswer("error"), dmarc=DnsAnswer("error"), caa=DnsAnswer("error"), ds=DnsAnswer("error")
    )
    assessment = assess(page(GOOD_HEADERS), good_tls(), clean_probes(), broken)
    assert not [f for f in assessment.findings if f.id.startswith("SS-DNS-")]
    skipped = {s.name for s in assessment.checks_skipped}
    assert {"email-spf", "email-dmarc", "dns-caa", "dnssec"} <= skipped
    assert {"SS-DNS-SPF-", "SS-DNS-DMARC-", "SS-DNS-CAA-", "SS-DNS-DNSSEC-"} <= set(
        assessment.unverified_prefixes
    )


def test_a_subdomain_skips_the_dns_checks_with_a_reason() -> None:
    reason = "DNS and email checks apply to a main domain."
    assessment = assess(page(GOOD_HEADERS), good_tls(), clean_probes(), reason)
    assert [s.reason for s in assessment.checks_skipped if s.name == "email-spf"] == [reason]


def test_callers_that_do_no_dns_checks_see_no_dns_checks() -> None:
    assessment = assess(page(GOOD_HEADERS), good_tls(), clean_probes())
    assert not [c for c in assessment.checks_run if c.startswith(("email-", "dns", "dnssec"))]
    assert assessment.checks_skipped == []


def test_the_new_checks_cost_a_site_with_nothing_set_only_a_few_points() -> None:
    assessment = assess(page(GOOD_HEADERS), good_tls(), clean_probes(), dns())
    new = sorted(f.id for f in assessment.findings if f.id.startswith("SS-DNS-"))
    assert new == ["SS-DNS-CAA-001", "SS-DNS-DMARC-001", "SS-DNS-DNSSEC-001", "SS-DNS-SPF-001"]
    score, grade = compute_score([f for f in assessment.findings if f.id.startswith("SS-DNS-")])
    assert (score, grade) == (92, "A")  # two low findings, two informational ones


def test_observe_dns_asks_only_for_the_verified_domain() -> None:
    asked: list[tuple[str, str]] = []

    async def fake(name: str, rdtype: str) -> DnsAnswer:
        asked.append((name, rdtype))
        return DnsAnswer("none")

    observation = asyncio.run(observe_dns("example.com", fake))
    assert sorted(asked) == [
        ("_dmarc.example.com", "TXT"),
        ("example.com", "CAA"),
        ("example.com", "DS"),
        ("example.com", "TXT"),
    ]
    assert observation.domain == "example.com"
