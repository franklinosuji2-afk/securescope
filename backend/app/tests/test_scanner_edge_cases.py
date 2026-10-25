"""Edge cases for the rules that had the fewest tests: each pins what a rule does and does not report."""

from __future__ import annotations

from typing import Any

import pytest

from app.scanner.dns_checks import DnsAnswer, check_dmarc, check_spf
from app.scanner.page_checks import check_cors, check_robots_and_sitemap
from app.schemas.scan import Severity
from app.tests.test_scan_accuracy import GOOD_HEADERS, clean_probes, page, probe
from app.tests.test_wider_checks import dns, ids, ok

NONE = DnsAnswer("none")
ERROR = DnsAnswer("error")


def with_headers(*extra: tuple[str, str]) -> Any:
    return page([*GOOD_HEADERS, *extra])


# --- CORS ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([("access-control-allow-origin", "*")], []),  # a public API may do this on purpose
        ([("access-control-allow-origin", "https://app.example.com")], []),
        ([("access-control-allow-origin", "")], []),
        (
            [("access-control-allow-origin", "*"), ("access-control-allow-credentials", "true")],
            ["SS-CORS-001"],
        ),
        (
            [("access-control-allow-origin", "*"), ("access-control-allow-credentials", "TRUE")],
            ["SS-CORS-001"],
        ),
        ([("access-control-allow-origin", "*"), ("access-control-allow-credentials", "false")], []),
        ([("access-control-allow-origin", "null")], ["SS-CORS-002"]),
        ([("access-control-allow-origin", "NULL")], ["SS-CORS-002"]),
        (
            [
                ("access-control-allow-origin", "https://a.example"),
                ("access-control-allow-credentials", "true"),
            ],
            [],
        ),
    ],
)
def test_cors_reports_only_the_two_unsafe_shapes(headers: list[tuple[str, str]], expected: list[str]) -> None:
    found = check_cors(with_headers(*headers))
    assert ids(found) == expected
    assert all(f.severity == Severity.MEDIUM for f in found)


def test_cors_evidence_is_the_header_that_was_seen_and_nothing_else() -> None:
    found = check_cors(
        with_headers(
            ("access-control-allow-origin", "*"),
            ("access-control-allow-credentials", "true"),
            ("set-cookie", "sid=SECRET"),
        )
    )
    assert "Access-Control-Allow-Origin: *" in (found[0].evidence or "")
    assert "SECRET" not in (found[0].evidence or "")


# --- robots.txt and sitemap.xml ---------------------------------------------------------------------------


def run(robots: bytes | None = None, sitemap: bytes | None = None, **kw: Any) -> list[str]:
    extra: dict[str, Any] = {}
    if robots is not None:
        extra["/robots.txt"] = probe(
            "/robots.txt", kw.get("status", 200), robots, kw.get("type", "text/plain")
        )
    if sitemap is not None:
        extra["/sitemap.xml"] = probe(
            "/sitemap.xml", kw.get("status", 200), sitemap, kw.get("type", "application/xml")
        )
    return ids(check_robots_and_sitemap(page(GOOD_HEADERS), clean_probes(**extra)))


def test_a_sensitive_word_must_be_a_whole_path_part_not_a_piece_of_another_word() -> None:
    assert run(sitemap=b"<urlset><url><loc>https://example.com/badminton-club</loc></url></urlset>") == []
    assert run(sitemap=b"<urlset><url><loc>https://example.com/dbase-news</loc></url></urlset>") == []
    assert run(sitemap=b"<urlset><url><loc>https://example.com/admin</loc></url></urlset>") == [
        "SS-DISC-SITEMAP-001"
    ]
    assert run(sitemap=b"<urlset><url><loc>https://example.com/old/backup.zip</loc></url></urlset>") == [
        "SS-DISC-SITEMAP-001"
    ]


def test_addresses_on_other_sites_and_unsuccessful_answers_are_ignored() -> None:
    other = b"<urlset><url><loc>https://other.example/admin</loc></url></urlset>"
    assert run(sitemap=other) == []
    assert run(sitemap=b"<urlset><url><loc>https://example.com/admin</loc></url></urlset>", status=404) == []
    assert run(robots=b"Disallow: /admin\n", status=500) == []
    assert run(robots=b"", sitemap=b"") == []


def test_robots_comments_root_and_empty_rules_are_not_paths() -> None:
    assert run(robots=b"User-agent: *\nDisallow:\nDisallow: /\n# Disallow: /admin\n") == []
    assert run(robots=b"Disallow: /public # /admin is not here\n") == []
    assert run(robots=b"disallow: /Admin\n") == ["SS-DISC-ROBOTS-001"]  # case-insensitive keys and words


def test_a_long_list_is_cut_to_five_but_counted_in_full() -> None:
    body = b"Disallow: /admin0/\n"  # "admin0" is not the whole word "admin", so it is not counted
    body += b"".join(f"Disallow: /backup/{n}\n".encode() for n in range(9))
    found = check_robots_and_sitemap(
        page(GOOD_HEADERS), clean_probes(**{"/robots.txt": probe("/robots.txt", 200, body)})
    )
    evidence = found[0].evidence or ""
    assert evidence.startswith("9 path(s)") and evidence.count("/backup/") <= 5


# --- SPF ----------------------------------------------------------------------------------------------------


def test_spf_ignores_other_txt_records_and_matches_the_version_tag_in_any_case() -> None:
    assert ids(check_spf(dns(txt=ok("V=SPF1 -all", "google-site-verification=x")))) == []
    assert ids(check_spf(dns(txt=ok("v=spf1 -all", "V=SPF1 ~all")))) == ["SS-DNS-SPF-003"]
    assert ids(check_spf(dns(txt=ok("v=spf1 -all", "v=spf10 something")))) == []  # not an SPF version tag
    assert ids(check_spf(dns(txt=ok("v=spf1 -all", "spf2.0/pra mx -all")))) == []  # a different record type


def test_a_dns_error_is_not_a_missing_record() -> None:
    assert check_spf(dns(txt=ERROR)) == []
    assert check_dmarc(dns(dmarc=ERROR)) == []


# --- DMARC --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ("v=DMARC1; p=none", ["SS-DNS-DMARC-002"]),
        ("v=dmarc1; p=none; rua=mailto:r@example.com", ["SS-DNS-DMARC-002"]),
        ("v=DMARC1;p=none", ["SS-DNS-DMARC-002"]),
        ("v=DMARC1; p = none", ["SS-DNS-DMARC-002"]),
        ("v=DMARC1; sp=none; p=reject", []),  # the subdomain policy is not the domain policy
        ("v=DMARC1; p=reject; sp=none", []),
        ("v=DMARC1; p=quarantine", []),
        ("v=DMARC1; p=reject; pct=100", []),
        ("DMARC1; p=reject", ["SS-DNS-DMARC-001"]),  # no version tag: not a DMARC record
        ("v=DMARC2; p=reject", ["SS-DNS-DMARC-001"]),
    ],
)
def test_dmarc_reads_the_domain_policy_not_the_subdomain_policy(record: str, expected: list[str]) -> None:
    assert ids(check_dmarc(dns(dmarc=ok(record)))) == expected
