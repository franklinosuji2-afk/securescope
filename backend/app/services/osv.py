"""The OSV.dev vulnerability source for App Scanning (decision D-A, option 1: the server looks packages up).

Used only when SECURESCOPE_APP_OSV_ENABLED is on; the default source stays `UnavailableSource`. What leaves the
server is exactly what `docs/app-scanning-v1-privacy-and-licensing.md` section 1 lists: per package the ecosystem,
the name and the exact version, nothing else (no file names, project, workspace or user). One fixed host, no
redirects, capped response sizes, timeouts and a time budget per lookup.

Two calls, as documented at https://google.github.io/osv.dev/api/ (read 31 Oct 2026):
- POST /v1/querybatch answers, in the order asked, with the ids (and modified times) of the advisories that list
  each package version. It returns no details.
- GET /v1/vulns/{id} returns one full record, from which the summary, severity, fixed versions, aliases and
  reference links are taken.

Anything that is not a clean answer is reported as no answer for that package, so the scan says "incomplete"
instead of "clean": a failed batch, a record that could not be fetched, a result that is paginated (more advisories
than one reply holds), or a reply that does not line up with the request. Error text is never passed on."""

from __future__ import annotations

import json
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from app.appscan.cvss import base_score
from app.appscan.manifests import Package
from app.appscan.vulns import Advisory, LookupResult, SourceInfo, SourceUnavailable

OSV_API = "https://api.osv.dev"
BATCH_BYTES = 8 * 1024 * 1024
RECORD_BYTES = 1024 * 1024
CACHE_ENTRIES = 2_000
FETCH_WORKERS = 8
_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
ATTRIBUTION = (
    "Advisory data from OSV.dev, which aggregates sources such as the GitHub Advisory Database and the PyPA "
    "Advisory Database (both CC-BY 4.0). Follow the links on each finding for the original advisory."
)
SOURCE = SourceInfo(name="OSV.dev", version="v1", attribution=ATTRIBUTION)


def _pypi_name(name: str) -> str:
    """PEP 503 normalisation, which OSV also applies to PyPI names."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _same_package(ecosystem: str, name: str, package: Package) -> bool:
    if ecosystem != package.ecosystem:
        return False
    if ecosystem == "PyPI":
        return _pypi_name(name) == _pypi_name(package.name)
    return name == package.name


def _release(version: str) -> tuple[int, ...] | None:
    """The leading release numbers of a version ("1.2.6" -> (1, 2, 6), "2.3.0rc1" -> (2, 3, 0)). Good enough to
    tell which affected range a version is in; anything without leading numbers gives None."""
    match = re.match(r"^v?(\d+(?:\.\d+)*)", version.strip())
    if not match:
        return None
    parts = [int(part) for part in match.group(1).split(".")]
    return tuple(parts + [0] * (4 - len(parts)))  # so 1.2 and 1.2.0 compare equal


def _words(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def advisory_for(record: dict[str, Any], package: Package) -> Advisory | None:
    """Turns one OSV record into the advisory for `package`. Only fields the schema defines are read; anything of
    the wrong type is ignored. The pipeline cleans and caps every text again before it is stored."""
    vuln_id = record.get("id")
    if not isinstance(vuln_id, str) or not _ID.match(vuln_id):
        return None
    affected = [
        a
        for a in record.get("affected") or []
        if isinstance(a, dict)
        and isinstance(a.get("package"), dict)
        and _same_package(str(a["package"].get("ecosystem", "")), str(a["package"].get("name", "")), package)
    ]
    fixed: list[str] = []
    matching: list[str] = []
    severity: str | None = None
    installed = _release(package.version)
    for entry in affected:
        specific = entry.get("ecosystem_specific")
        if severity is None and isinstance(specific, dict):
            severity = _words(specific.get("severity"))
        for rng in entry.get("ranges") or []:
            if not isinstance(rng, dict) or rng.get("type") not in ("ECOSYSTEM", "SEMVER"):
                continue
            start: tuple[int, ...] | None = None
            for event in rng.get("events") or []:
                if not isinstance(event, dict):
                    continue
                if isinstance(event.get("introduced"), str):
                    start = _release(event["introduced"])
                if isinstance(event.get("fixed"), str):
                    if event["fixed"] not in fixed:
                        fixed.append(event["fixed"])
                    end = _release(event["fixed"])
                    if installed and start is not None and end and start <= installed < end:
                        matching.append(event["fixed"])
                    start = None
    # The fix for the range the installed version is in (for example 1.2.6, not the 0.2.4 of an older line). When
    # the versions cannot be compared, every fixed version is listed rather than guessing.
    fixed = matching or fixed
    database = record.get("database_specific")
    if severity is None and isinstance(database, dict):
        severity = _words(database.get("severity"))
    if severity is None:
        for item in record.get("severity") or []:
            if (
                isinstance(item, dict)
                and item.get("type") == "CVSS_V3"
                and isinstance(item.get("score"), str)
            ):
                score = base_score(item["score"])
                if score is not None:
                    severity = f"{score:.1f}"
                    break
    summary = _words(record.get("summary")) or _words(record.get("details")) or ""
    references = tuple(
        r["url"]
        for r in record.get("references") or []
        if isinstance(r, dict) and isinstance(r.get("url"), str)
    )
    aliases = tuple(a for a in record.get("aliases") or [] if isinstance(a, str))
    return Advisory(
        id=vuln_id,
        summary=summary[:2000],
        aliases=aliases,
        severity=severity,
        fixed_versions=tuple(fixed),
        references=references,
    )


class OsvSource:
    max_batch = 500

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        budget_seconds: float = 15.0,
        clock: Any = time.monotonic,
    ) -> None:
        self._transport = transport
        self._budget = budget_seconds
        self._clock = clock
        self._cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=OSV_API,
            transport=self._transport,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": "SecureScope-AppScanning", "Accept": "application/json"},
            limits=httpx.Limits(max_connections=FETCH_WORKERS, max_keepalive_connections=FETCH_WORKERS),
        )

    @staticmethod
    def _json(client: httpx.Client, method: str, url: str, limit: int, body: object = None) -> Any:
        with client.stream(method, url, json=body) as response:
            if response.status_code != 200:
                raise SourceUnavailable
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > limit:
                    raise SourceUnavailable
                chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except ValueError:
            raise SourceUnavailable from None

    def _record(self, client: httpx.Client, vuln_id: str, modified: str, deadline: float) -> dict[str, Any]:
        key = (vuln_id, modified)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        if self._clock() > deadline:
            raise SourceUnavailable
        record = self._json(client, "GET", f"/v1/vulns/{vuln_id}", RECORD_BYTES)
        if not isinstance(record, dict) or record.get("id") != vuln_id:
            raise SourceUnavailable
        with self._lock:
            self._cache[key] = record
            while len(self._cache) > CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return record

    def lookup(self, packages: Sequence[Package]) -> LookupResult:
        deadline = self._clock() + self._budget
        if not packages:
            return LookupResult(advisories=[], info=SOURCE)
        queries = [
            {"package": {"name": p.name, "ecosystem": p.ecosystem}, "version": p.version} for p in packages
        ]
        try:
            with self._client() as client:
                reply = self._json(client, "POST", "/v1/querybatch", BATCH_BYTES, {"queries": queries})
                results = reply.get("results") if isinstance(reply, dict) else None
                if not isinstance(results, list) or len(results) != len(packages):
                    raise SourceUnavailable
                wanted: list[list[tuple[str, str]] | None] = []
                for result in results:
                    if not isinstance(result, dict) or result.get("next_page_token"):
                        wanted.append(None)  # not a complete answer for this package
                        continue
                    vulns = [v for v in result.get("vulns") or [] if isinstance(v, dict)]
                    if all(isinstance(v.get("id"), str) and _ID.match(v["id"]) for v in vulns):
                        wanted.append([(v["id"], str(v.get("modified", ""))) for v in vulns])
                    else:
                        wanted.append(None)  # an advisory we cannot read must not make the package look clean
                unique = sorted({item for ids in wanted if ids for item in ids})
                records: dict[tuple[str, str], dict[str, Any] | None] = {}

                def fetch(item: tuple[str, str]) -> None:
                    try:
                        records[item] = self._record(client, item[0], item[1], deadline)
                    except (SourceUnavailable, httpx.HTTPError):
                        records[item] = None

                with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
                    list(pool.map(fetch, unique))
        except (httpx.HTTPError, SourceUnavailable):
            raise SourceUnavailable from None

        answers: list[list[Advisory] | None] = []
        for package, asked in zip(packages, wanted, strict=True):
            if asked is None:
                answers.append(None)
                continue
            found: list[Advisory] = []
            complete = True
            for item in asked:
                record = records.get(item)
                if record is None:
                    complete = False
                    break
                advisory = advisory_for(record, package)
                if advisory is not None:
                    found.append(advisory)
            answers.append(_without_aliases(found) if complete else None)
        return LookupResult(advisories=answers, info=SOURCE)


def _without_aliases(found: list[Advisory]) -> list[Advisory]:
    """One issue is often published by several databases (a GHSA and a PYSEC record naming each other as aliases).
    Keep one per issue, preferring the record that gives a severity, so one problem is not counted twice."""
    kept: list[Advisory] = []
    seen: set[str] = set()
    for advisory in sorted(found, key=lambda a: (a.severity is None, a.id)):
        names = {advisory.id, *advisory.aliases}
        if names & seen:
            continue
        seen |= names
        kept.append(advisory)
    return kept
