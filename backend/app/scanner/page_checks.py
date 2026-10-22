"""Passive checks on the page the scan already fetched: insecure resources, third-party scripts without an
integrity hash, risky cross-origin headers, and paths that robots.txt or sitemap.xml point at.

Nothing here sends traffic. The HTML is read from the capped body sample the fetcher kept in memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.scanner.fetcher import FetchResult, ProbeResponse
from app.schemas.scan import Finding, Severity

MAX_LISTED = 5
SENSITIVE_PATH = re.compile(
    r"(?:^|[/_.-])(?:admin|administrator|backup|backups|bak|staging|stage|internal|private|secret|secrets|"
    r"config|configs|database|db|dump|dumps|phpmyadmin|cpanel|\.git|\.env|\.svn|passwd|credentials|debug)"
    r"(?:$|[/_.-])",
    re.IGNORECASE,
)


def _site_key(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _short(url: str, limit: int = 120) -> str:
    """A resource address without its query or fragment, which can carry tokens."""
    parts = urlsplit(url)
    text = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else url.split("?")[0].split("#")[0]
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class _Resource:
    tag: str
    url: str
    has_integrity: bool = False
    rel: str = ""


@dataclass
class _PageResources(HTMLParser):
    resources: list[_Resource] = field(default_factory=list)

    def __post_init__(self) -> None:
        HTMLParser.__init__(self, convert_charrefs=True)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and a.get("src"):
            self.resources.append(_Resource("script", a["src"].strip(), "integrity" in a))
        elif tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            if "stylesheet" in rel or "preload" in rel or "modulepreload" in rel:
                self.resources.append(_Resource("link", a["href"].strip(), "integrity" in a, rel))
        elif tag in ("img", "audio", "video", "source", "track") and a.get("src"):
            self.resources.append(_Resource(tag, a["src"].strip()))
        elif tag in ("iframe", "embed", "frame") and a.get("src"):
            self.resources.append(_Resource(tag, a["src"].strip()))
        elif tag == "object" and a.get("data"):
            self.resources.append(_Resource(tag, a["data"].strip()))
        elif tag == "form" and a.get("action"):
            self.resources.append(_Resource("form", a["action"].strip()))


def _is_html(result: FetchResult) -> bool:
    kind = result.headers.get("content-type", "").lower()
    return "html" in kind


def page_resources(result: FetchResult) -> list[_Resource]:
    if not _is_html(result) or not result.body_sample:
        return []
    parser = _PageResources()
    try:
        parser.feed(result.body_sample.decode("utf-8", errors="replace"))
        parser.close()
    except (ValueError, AssertionError):  # malformed markup must never fail a scan; keep what was read
        return parser.resources
    return parser.resources


def _listing(urls: list[str]) -> str:
    shown = [_short(u) for u in urls[:MAX_LISTED]]
    more = len(urls) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def check_mixed_content(result: FetchResult) -> list[Finding]:
    if result.final_scheme != "https":
        return []  # over plain HTTP the page itself is the problem, reported by the HTTPS check
    active: list[str] = []
    passive: list[str] = []
    for r in page_resources(result):
        if not r.url.lower().startswith("http://"):
            continue
        if r.tag in ("img", "audio", "video", "source", "track"):
            passive.append(r.url)
        elif r.tag == "link" and "stylesheet" not in r.rel:
            passive.append(r.url)
        else:
            active.append(r.url)
    findings: list[Finding] = []
    if active:
        findings.append(
            Finding(
                id="SS-MIX-001",
                title="The page loads scripts, styles, frames or forms over plain HTTP",
                severity=Severity.MEDIUM,
                category="Page content",
                description=(
                    "An HTTPS page that pulls in code, frames or form targets over HTTP can be tampered with "
                    "by anyone on the network. Browsers usually block these, which breaks the page, and a "
                    "form that submits to HTTP sends what visitors type unencrypted."
                ),
                evidence=f"{len(active)} resource(s) in the page markup use http://: {_listing(active)}",
                remediation=(
                    "Change each address to https:// (or a protocol-relative path), and make sure the other "
                    "host serves it over HTTPS."
                ),
            )
        )
    if passive:
        findings.append(
            Finding(
                id="SS-MIX-002",
                title="The page loads images or media over plain HTTP",
                severity=Severity.LOW,
                category="Page content",
                description=(
                    "Images and media loaded over HTTP can be swapped or observed on the network, and "
                    "browsers show the page as not fully secure."
                ),
                evidence=f"{len(passive)} resource(s) in the page markup use http://: {_listing(passive)}",
                remediation="Change each address to https:// and check that the other host supports it.",
            )
        )
    return findings


def check_subresource_integrity(result: FetchResult) -> list[Finding]:
    host = _site_key(result.host)
    missing: list[str] = []
    for r in page_resources(result):
        if r.tag not in ("script", "link") or r.has_integrity:
            continue
        if r.tag == "link" and "stylesheet" not in r.rel:
            continue
        parts = urlsplit(r.url if "://" in r.url else ("https:" + r.url if r.url.startswith("//") else ""))
        if parts.scheme in ("http", "https") and parts.hostname and _site_key(parts.hostname) != host:
            missing.append(r.url if "://" in r.url else "https:" + r.url)
    if not missing:
        return []
    return [
        Finding(
            id="SS-SRI-001",
            title="Scripts or styles from other sites have no integrity hash",
            severity=Severity.LOW,
            category="Page content",
            description=(
                "If a third-party host is compromised, the code it serves runs on your page with full access "
                "to it. An integrity attribute makes the browser refuse a file that has changed."
            ),
            evidence=(
                f"{len(missing)} script or stylesheet address(es) on other sites have no integrity attribute: "
                f"{_listing(missing)}"
            ),
            remediation=(
                'Add integrity="sha384-..." and crossorigin="anonymous" to files that never change, or host '
                "the file yourself. Scripts that must stay current, such as some analytics tags, cannot use it."
            ),
        )
    ]


def check_cors(result: FetchResult) -> list[Finding]:
    origin = result.headers.get("access-control-allow-origin", "").strip()
    credentials = result.headers.get("access-control-allow-credentials", "").strip().lower() == "true"
    if not origin:
        return []
    header = f"Access-Control-Allow-Origin: {origin[:80]}" + (
        "; Access-Control-Allow-Credentials: true" if credentials else ""
    )
    if origin == "*" and credentials:
        return [
            Finding(
                id="SS-CORS-001",
                title="Cross-origin access is allowed for any site together with credentials",
                severity=Severity.MEDIUM,
                category="Cross-origin access",
                description=(
                    "The wildcard origin with credentials is invalid and browsers ignore it, but it shows the "
                    "policy was written without a list of trusted sites. Servers that fix this by echoing back "
                    "any origin let other websites read a signed-in visitor's data."
                ),
                evidence=f"Seen on the response from {result.final_url}: {header}",
                remediation=(
                    "Allow only the specific origins that need access, send Vary: Origin, and never combine "
                    "a wildcard with credentials."
                ),
            )
        ]
    if origin.lower() == "null":
        return [
            Finding(
                id="SS-CORS-002",
                title="Cross-origin access is allowed for the null origin",
                severity=Severity.MEDIUM,
                category="Cross-origin access",
                description=(
                    'Sandboxed frames, local files and some redirects send the origin "null". Allowing it '
                    "lets pages that anyone can build read responses from this site."
                ),
                evidence=f"Seen on the response from {result.final_url}: {header}",
                remediation="Remove null from the list of allowed origins.",
            )
        ]
    return []


def _paths_from_robots(text: str) -> list[str]:
    paths: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() in ("disallow", "allow"):
            value = value.split("#")[0].strip()
            if value and value != "/":
                paths.append(value)
    return paths


def _paths_from_sitemap(text: str, host: str) -> list[str]:
    paths: list[str] = []
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text, re.IGNORECASE):
        parts = urlsplit(loc)
        if parts.hostname and _site_key(parts.hostname) == _site_key(host):
            paths.append(parts.path or "/")
    return paths


def _sensitive(paths: list[str]) -> list[str]:
    seen: list[str] = []
    for path in paths:
        clean = path.split("?")[0]
        if SENSITIVE_PATH.search(clean) and clean not in seen:
            seen.append(clean)
    return seen


def _text_probe(probes: dict[str, ProbeResponse], path: str) -> str | None:
    response = probes.get(path)
    if response is None or response.error is not None or response.status != 200:
        return None
    kind = (response.content_type or "").lower()
    if "html" in kind:  # a single-page app answering every path with its home page
        return None
    return response.body_sample.decode("utf-8", errors="replace")


def check_robots_and_sitemap(result: FetchResult, probes: dict[str, ProbeResponse]) -> list[Finding]:
    findings: list[Finding] = []
    robots = _text_probe(probes, "/robots.txt")
    if robots is not None:
        hits = _sensitive(_paths_from_robots(robots))
        if hits:
            findings.append(
                Finding(
                    id="SS-DISC-ROBOTS-001",
                    title="robots.txt points at paths that look sensitive",
                    severity=Severity.INFO,
                    category="Information disclosure",
                    description=(
                        "robots.txt is public and is read by everyone, not only search engines. Listing an "
                        "admin, backup or configuration path there tells a visitor exactly where to look. "
                        "Hiding a path this way does not protect it."
                    ),
                    evidence=f"{len(hits)} path(s) in /robots.txt match sensitive names: {', '.join(hits[:MAX_LISTED])}",
                    remediation=(
                        "Protect these paths with authentication or remove them from the server, and keep "
                        "robots.txt to what you want search engines to skip."
                    ),
                )
            )
    sitemap = _text_probe(probes, "/sitemap.xml")
    if sitemap is not None:
        hits = _sensitive(_paths_from_sitemap(sitemap, result.host))
        if hits:
            findings.append(
                Finding(
                    id="SS-DISC-SITEMAP-001",
                    title="sitemap.xml lists addresses that look sensitive",
                    severity=Severity.INFO,
                    category="Information disclosure",
                    description=(
                        "A sitemap is meant to list public pages. Admin, backup or configuration addresses in "
                        "it are advertised to search engines and to anyone who opens the file."
                    ),
                    evidence=f"{len(hits)} address(es) in /sitemap.xml match sensitive names: {', '.join(hits[:MAX_LISTED])}",
                    remediation="Remove these addresses from the sitemap and protect them with authentication.",
                )
            )
    return findings
