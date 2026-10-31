"""The OSV.dev source: what is sent (only ecosystem, name and exact version, to one fixed host), how records become
advisories, and that every imperfect answer is reported as "no answer" so a scan is never shown as clean. All
replies are mocked; no test opens a network connection."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.appscan.cvss import base_score
from app.appscan.manifests import Package
from app.appscan.vulns import SourceUnavailable, UnavailableSource
from app.main import create_app
from app.services.osv import ATTRIBUTION, OsvSource
from app.tests.conftest import signup

API = "/api/v1/app"
LODASH = Package("npm", "lodash", "4.17.20", "package-lock.json")
FLASK = Package("PyPI", "Flask", "2.2.0", "requirements.txt")
GHSA = {
    "id": "GHSA-35jh-r3h4-6jhm",
    "modified": "2026-01-01T00:00:00Z",
    "summary": "Command Injection in lodash",
    "aliases": ["CVE-2021-23337"],
    "database_specific": {"severity": "HIGH"},
    "affected": [
        {
            "package": {"ecosystem": "npm", "name": "lodash"},
            "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}],
        }
    ],
    "references": [{"type": "ADVISORY", "url": "https://github.com/advisories/GHSA-35jh-r3h4-6jhm"}],
}
PYSEC = {
    "id": "PYSEC-2023-62",
    "modified": "2026-01-02T00:00:00Z",
    "details": "Flask may cache a response with a session cookie.",
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N"}],
    "affected": [
        {
            "package": {"ecosystem": "PyPI", "name": "flask"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.2.5"}]},
                {"type": "ECOSYSTEM", "events": [{"introduced": "2.3.0"}, {"fixed": "2.3.2"}]},
            ],
        }
    ],
}
RECORDS = {r["id"]: r for r in (GHSA, PYSEC)}


class Osv:
    """A stand-in for api.osv.dev that records every request."""

    def __init__(self, table: dict[str, list[str]], **overrides: Any) -> None:
        self.table = table
        self.overrides = overrides
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/querybatch":
            if "batch" in self.overrides:
                answer: httpx.Response = self.overrides["batch"](request)
                return answer
            queries = json.loads(request.content)["queries"]
            results = [
                {
                    "vulns": [
                        {"id": i, "modified": RECORDS[i]["modified"]}
                        for i in self.table.get(q["package"]["name"], [])
                    ]
                }
                for q in queries
            ]
            return httpx.Response(200, json={"results": results})
        vuln_id = request.url.path.rsplit("/", 1)[-1]
        if vuln_id in self.overrides.get("missing", ()):
            return httpx.Response(404, json={"code": 5, "message": "Bug not found."})
        return httpx.Response(200, json=RECORDS[vuln_id])


def source(osv: Osv) -> OsvSource:
    return OsvSource(transport=httpx.MockTransport(osv))


# --- what is sent --------------------------------------------------------------------------------------------


def test_only_ecosystem_name_and_version_are_sent_to_the_fixed_host() -> None:
    osv = Osv({"lodash": ["GHSA-35jh-r3h4-6jhm"]})
    source(osv).lookup([LODASH, FLASK])
    assert {r.url.host for r in osv.requests} == {"api.osv.dev"}
    assert all(r.url.scheme == "https" for r in osv.requests)
    batch = next(r for r in osv.requests if r.url.path == "/v1/querybatch")
    assert json.loads(batch.content) == {
        "queries": [
            {"package": {"name": "lodash", "ecosystem": "npm"}, "version": "4.17.20"},
            {"package": {"name": "Flask", "ecosystem": "PyPI"}, "version": "2.2.0"},
        ]
    }
    # Nothing about the file, project, workspace or user travels with the request.
    sent = b" ".join(r.content for r in osv.requests) + str([dict(r.headers) for r in osv.requests]).encode()
    for word in (b"package-lock.json", b"requirements.txt", b"cookie", b"authorization"):
        assert word not in sent.lower()
    assert [r.url.path for r in osv.requests if r.method == "GET"] == ["/v1/vulns/GHSA-35jh-r3h4-6jhm"]


def test_a_redirect_is_not_followed() -> None:
    def moved(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://elsewhere.example/"})

    osv = Osv({}, batch=moved)
    with pytest.raises(SourceUnavailable):
        source(osv).lookup([LODASH])
    assert [r.url.host for r in osv.requests] == ["api.osv.dev"]


# --- how records become advisories ---------------------------------------------------------------------------


def test_records_give_severity_fixed_versions_aliases_and_links() -> None:
    reply = source(Osv({"lodash": ["GHSA-35jh-r3h4-6jhm"], "Flask": ["PYSEC-2023-62"]})).lookup(
        [LODASH, FLASK]
    )
    assert reply.info.name == "OSV.dev" and reply.info.attribution == ATTRIBUTION
    lodash, flask = reply.advisories
    assert lodash is not None and flask is not None
    (ghsa,) = lodash
    assert (ghsa.id, ghsa.severity, ghsa.fixed_versions, ghsa.aliases) == (
        "GHSA-35jh-r3h4-6jhm",
        "HIGH",
        ("4.17.21",),
        ("CVE-2021-23337",),
    )
    assert ghsa.references == ("https://github.com/advisories/GHSA-35jh-r3h4-6jhm",)
    (pysec,) = flask
    # Only a CVSS vector is given, so the base score is computed from it; the PyPI name matches case-insensitively.
    assert pysec.severity == "5.9"
    # 2.2.0 is in the first affected range, so only that range's fix is offered.
    assert pysec.fixed_versions == ("2.2.5",)
    assert pysec.summary.startswith("Flask may cache")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.5", ("1.2.6",)),
        ("0.2.1", ("0.2.4",)),
        ("v1.2", ("1.2.6",)),
        # Not comparable, so every fix is listed instead of a guess.
        ("main", ("0.2.4", "1.2.6")),
    ],
)
def test_the_fix_offered_is_the_one_for_the_installed_line(version: str, expected: tuple[str, ...]) -> None:
    from app.services.osv import advisory_for

    record = {
        "id": "GHSA-xvch-5gv4-984h",
        "affected": [
            {
                "package": {"ecosystem": "npm", "name": "minimist"},
                "ranges": [
                    {"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "0.2.4"}]},
                    {"type": "SEMVER", "events": [{"introduced": "1.0.0"}, {"fixed": "1.2.6"}]},
                ],
            }
        ],
    }
    advisory = advisory_for(record, Package("npm", "minimist", version, "package-lock.json"))
    assert advisory is not None and advisory.fixed_versions == expected


def test_the_same_issue_from_two_databases_is_counted_once() -> None:
    twin = {
        **PYSEC,
        "id": "GHSA-m2qf-hxjv-5gpq",
        "aliases": ["PYSEC-2023-62"],
        "database_specific": {"severity": "HIGH"},
    }
    RECORDS[twin["id"]] = twin
    try:
        (flask,) = source(Osv({"Flask": ["PYSEC-2023-62", "GHSA-m2qf-hxjv-5gpq"]})).lookup([FLASK]).advisories
    finally:
        del RECORDS[twin["id"]]
    assert flask is not None
    assert [(a.id, a.severity) for a in flask] == [("GHSA-m2qf-hxjv-5gpq", "HIGH")]


def test_a_package_without_advisories_is_an_answer_not_a_gap() -> None:
    reply = source(Osv({})).lookup([LODASH])
    assert reply.advisories == [[]]


def test_records_are_cached_by_id_and_modified_time() -> None:
    osv = Osv({"lodash": ["GHSA-35jh-r3h4-6jhm"]})
    src = source(osv)
    src.lookup([LODASH])
    src.lookup([LODASH])
    assert [r.url.path for r in osv.requests].count("/v1/vulns/GHSA-35jh-r3h4-6jhm") == 1


# --- imperfect answers are gaps, never clean results ---------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(429, text="slow down"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"results": []}),  # does not line up with the request
        httpx.Response(200, json=["unexpected"]),
    ],
)
def test_a_failed_batch_means_the_source_is_unavailable(reply: httpx.Response) -> None:
    with pytest.raises(SourceUnavailable):
        source(Osv({}, batch=lambda request: reply)).lookup([LODASH])


def test_a_network_error_means_the_source_is_unavailable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(SourceUnavailable):
        source(Osv({}, batch=down)).lookup([LODASH])


def test_an_oversized_reply_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.osv.BATCH_BYTES", 100)
    with pytest.raises(SourceUnavailable):
        source(Osv({}, batch=lambda request: httpx.Response(200, text="x" * 1000))).lookup([LODASH])


def test_a_record_that_cannot_be_fetched_leaves_only_that_package_unanswered() -> None:
    osv = Osv(
        {"lodash": ["GHSA-35jh-r3h4-6jhm"], "Flask": ["PYSEC-2023-62"]}, missing=("GHSA-35jh-r3h4-6jhm",)
    )
    lodash, flask = source(osv).lookup([LODASH, FLASK]).advisories
    assert lodash is None
    assert flask is not None and len(flask) == 1


def test_a_paginated_result_is_not_treated_as_complete() -> None:
    def paged(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [{"vulns": [{"id": "GHSA-35jh-r3h4-6jhm"}], "next_page_token": "abc"}]}
        )

    assert source(Osv({}, batch=paged)).lookup([LODASH]).advisories == [None]


def test_an_unreadable_advisory_id_leaves_the_package_unanswered() -> None:
    def odd(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"vulns": [{"id": "../../etc"}]}]})

    assert source(Osv({}, batch=odd)).lookup([LODASH]).advisories == [None]


def test_records_are_not_fetched_after_the_time_budget() -> None:
    ticks = iter([0.0, 100.0, 100.0, 100.0])
    osv = Osv({"lodash": ["GHSA-35jh-r3h4-6jhm"]})
    src = OsvSource(transport=httpx.MockTransport(osv), budget_seconds=1.0, clock=lambda: next(ticks))
    assert src.lookup([LODASH]).advisories == [None]
    assert all(r.method == "POST" for r in osv.requests)


# --- CVSS ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vector", "score"),
    [
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),
        ("CVSS:3.0/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N", 5.9),
        ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 7.8),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
    ],
)
def test_cvss_base_scores_match_the_specification(vector: str, score: float) -> None:
    assert base_score(vector) == score


@pytest.mark.parametrize(
    "vector",
    [
        "",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H",
        "CVSS:3.1/AV:X/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:3.1/AV:N/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    ],
)
def test_an_unusable_vector_gives_no_score(vector: str) -> None:
    assert base_score(vector) is None


# --- wiring --------------------------------------------------------------------------------------------------


def test_the_source_is_osv_only_when_switched_on(make_settings: Any, mailer: Any) -> None:
    with TestClient(create_app(make_settings(app_scanning_enabled=True), mailer)) as client:
        assert isinstance(client.app.state.s.app_source, UnavailableSource)  # type: ignore[attr-defined]
        signup(client, "owner@example.com", "Org")
        assert client.get(f"{API}/overview").json()["lookups_available"] is False
    with TestClient(
        create_app(make_settings(app_scanning_enabled=True, app_osv_enabled=True), mailer)
    ) as client:
        assert isinstance(client.app.state.s.app_source, OsvSource)  # type: ignore[attr-defined]
        signup(client, "second@example.com", "Org 2")
        assert client.get(f"{API}/overview").json()["lookups_available"] is True


def test_a_browser_scan_through_osv_reports_findings_with_attribution(
    make_settings: Any, mailer: Any
) -> None:
    lock = json.dumps(
        {"lockfileVersion": 3, "packages": {"": {"name": "x"}, "node_modules/lodash": {"version": "4.17.20"}}}
    )
    with TestClient(create_app(make_settings(app_scanning_enabled=True), mailer)) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = source(Osv({"lodash": ["GHSA-35jh-r3h4-6jhm"]}))  # type: ignore[attr-defined]
        project_id = client.post(f"{API}/projects", json={"name": "web"}).json()["id"]
        response = client.post(
            f"{API}/scans",
            json={"project_id": project_id, "files": [{"name": "package-lock.json", "content": lock}]},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["result"] == "completed_findings"
        assert body["counts"]["high"] == 1
        (finding,) = body["findings"]
        assert finding["rule_id"] == "GHSA-35jh-r3h4-6jhm"
        assert finding["fixed_versions"] == ["4.17.21"]
        assert body["attribution"] == ATTRIBUTION
        assert client.get(f"{API}/overview").json()["usage"]["runs_used"] == 1
