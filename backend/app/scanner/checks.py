"""Passive checks. Pure functions: response metadata in, findings out.

Nothing here sends traffic. Checks are deliberately limited and conservative; they look at the
single response the fetcher already obtained.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.scanner.fetcher import FetchResult
from app.schemas.scan import Finding, Severity

HSTS_MIN_SECONDS = 15_552_000  # 180 days
VERSION_IN_HEADER = re.compile(r"\d+\.\d+")
DIRECTORY_INDEX_SIGNATURES: tuple[re.Pattern[str], ...] = (
    re.compile(r"<title>\s*index of\s*/", re.IGNORECASE),
    re.compile(r"<h1>\s*index of\s*/", re.IGNORECASE),
    re.compile(r"<title>\s*directory listing for\s*/", re.IGNORECASE),
    re.compile(r"<h1>\s*directory listing for\s*/", re.IGNORECASE),
)


def _truncate(value: str, limit: int = 200) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def check_https(result: FetchResult) -> list[Finding]:
    if result.final_scheme == "http":
        return [
            Finding(
                id="SS-TLS-001",
                title="Site is served over unencrypted HTTP",
                severity=Severity.HIGH,
                category="Transport security",
                description=(
                    "The page was delivered without TLS, so traffic can be read or modified "
                    "by anyone on the network path."
                ),
                evidence=f"Final URL scheme: http ({result.final_url})",
                remediation=(
                    "Serve the site over HTTPS with a valid certificate and redirect all HTTP "
                    "requests to HTTPS."
                ),
            )
        ]
    if result.started_scheme == "http":
        return [
            Finding(
                id="SS-TLS-002",
                title="HTTP redirects to HTTPS",
                severity=Severity.INFO,
                category="Transport security",
                description="The plain HTTP address redirected to HTTPS, which is the desired behavior.",
                evidence=f"{result.redirect_chain[0]} -> {result.final_url}",
                remediation="No action needed. Consider enabling HSTS so browsers skip the redirect.",
            )
        ]
    return []


def check_hsts(result: FetchResult) -> list[Finding]:
    if result.final_scheme != "https":
        return []  # HSTS is only meaningful over HTTPS (and is ignored by browsers over HTTP).
    value = result.headers.get("strict-transport-security")
    if value is None:
        return [
            Finding(
                id="SS-HDR-HSTS-001",
                title="Strict-Transport-Security header is missing",
                severity=Severity.MEDIUM,
                category="Security headers",
                description=(
                    "Without HSTS, browsers may still attempt plain HTTP connections, which "
                    "enables downgrade and protocol-stripping attacks on first or later visits."
                ),
                evidence="Header not present in the response.",
                remediation=(
                    "Send 'Strict-Transport-Security: max-age=31536000; includeSubDomains' "
                    "once every subdomain is reachable over HTTPS."
                ),
            )
        ]
    match = re.search(r"max-age\s*=\s*(\d+)", value, re.IGNORECASE)
    max_age = int(match.group(1)) if match else 0
    if max_age < HSTS_MIN_SECONDS:
        return [
            Finding(
                id="SS-HDR-HSTS-002",
                title="Strict-Transport-Security max-age is short",
                severity=Severity.LOW,
                category="Security headers",
                description="A short HSTS lifetime reduces how long browsers enforce HTTPS.",
                evidence=f"Strict-Transport-Security: {_truncate(value)}",
                remediation="Use a max-age of at least 15552000 seconds (180 days); 1 year is common.",
            )
        ]
    return []


def check_csp(result: FetchResult) -> list[Finding]:
    value = result.headers.get("content-security-policy")
    if value is None:
        return [
            Finding(
                id="SS-HDR-CSP-001",
                title="Content-Security-Policy header is missing",
                severity=Severity.MEDIUM,
                category="Security headers",
                description=(
                    "A Content-Security-Policy limits where scripts and other resources can "
                    "load from and reduces the impact of cross-site scripting."
                ),
                evidence="Header not present in the response.",
                remediation=(
                    "Define a CSP that restricts script sources, e.g. start in report-only mode "
                    "with \"default-src 'self'\" and tighten from there."
                ),
            )
        ]
    directives = {
        part.strip().split(None, 1)[0].lower(): part.strip() for part in value.split(";") if part.strip()
    }
    script_policy = directives.get("script-src") or directives.get("default-src") or ""
    if "'unsafe-inline'" in script_policy or "'unsafe-eval'" in script_policy:
        return [
            Finding(
                id="SS-HDR-CSP-002",
                title="Content-Security-Policy allows unsafe script execution",
                severity=Severity.LOW,
                category="Security headers",
                description=(
                    "The policy permits 'unsafe-inline' or 'unsafe-eval' for scripts, which "
                    "weakens the protection against cross-site scripting."
                ),
                evidence=_truncate(script_policy),
                remediation="Use nonces or hashes instead of 'unsafe-inline', and remove 'unsafe-eval'.",
            )
        ]
    return []


def check_content_type_options(result: FetchResult) -> list[Finding]:
    value = (result.headers.get("x-content-type-options") or "").strip().lower()
    if value == "nosniff":
        return []
    return [
        Finding(
            id="SS-HDR-XCTO-001",
            title="X-Content-Type-Options: nosniff is missing",
            severity=Severity.LOW,
            category="Security headers",
            description="Browsers may MIME-sniff responses, which can turn some uploads into executable content.",
            evidence="Header not present." if not value else f"X-Content-Type-Options: {_truncate(value)}",
            remediation="Send 'X-Content-Type-Options: nosniff' on all responses.",
        )
    ]


def check_referrer_policy(result: FetchResult) -> list[Finding]:
    if result.headers.get("referrer-policy") is not None:
        return []
    return [
        Finding(
            id="SS-HDR-REF-001",
            title="Referrer-Policy header is missing",
            severity=Severity.LOW,
            category="Security headers",
            description="Without a policy, full URLs may be sent to other sites in the Referer header.",
            evidence="Header not present in the response.",
            remediation="Send 'Referrer-Policy: strict-origin-when-cross-origin' (or stricter).",
        )
    ]


def check_permissions_policy(result: FetchResult) -> list[Finding]:
    if result.headers.get("permissions-policy") is not None:
        return []
    return [
        Finding(
            id="SS-HDR-PERM-001",
            title="Permissions-Policy header is missing",
            severity=Severity.INFO,
            category="Security headers",
            description="A Permissions-Policy lets you disable powerful browser features the site does not use.",
            evidence="Header not present in the response.",
            remediation="Add a Permissions-Policy that disables unused features, e.g. 'camera=(), microphone=(), geolocation=()'.",
        )
    ]


def check_disclosure_headers(result: FetchResult) -> list[Finding]:
    findings: list[Finding] = []
    server = result.headers.get("server")
    if server:
        if VERSION_IN_HEADER.search(server):
            findings.append(
                Finding(
                    id="SS-DISC-SRV-001",
                    title="Server header discloses a software version",
                    severity=Severity.LOW,
                    category="Information disclosure",
                    description="Version details help attackers match the server to known vulnerabilities.",
                    evidence=f"Server: {_truncate(server)}",
                    remediation="Remove the version from the Server header or suppress the header at the proxy.",
                )
            )
        else:
            findings.append(
                Finding(
                    id="SS-DISC-SRV-002",
                    title="Server header is present",
                    severity=Severity.INFO,
                    category="Information disclosure",
                    description="The server announces its software name. This is minor but unnecessary.",
                    evidence=f"Server: {_truncate(server)}",
                    remediation="Consider removing or genericizing the Server header.",
                )
            )
    powered_by = result.headers.get("x-powered-by")
    if powered_by:
        findings.append(
            Finding(
                id="SS-DISC-XPB-001",
                title="X-Powered-By header discloses the technology stack",
                severity=Severity.LOW,
                category="Information disclosure",
                description="The header reveals framework or runtime details that are useful for targeting.",
                evidence=f"X-Powered-By: {_truncate(powered_by)}",
                remediation="Disable the X-Powered-By header in your framework or reverse proxy.",
            )
        )
    return findings


def _parse_cookie(raw: str) -> tuple[str, set[str], dict[str, str]]:
    """Return (cookie name, flag attributes, key=value attributes). The value is discarded."""
    parts = [p.strip() for p in raw.split(";")]
    name = parts[0].split("=", 1)[0].strip() if parts else ""
    flags: set[str] = set()
    attrs: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, val = part.split("=", 1)
            attrs[key.strip().lower()] = val.strip()
        elif part:
            flags.add(part.lower())
    return name, flags, attrs


def check_cookies(result: FetchResult) -> list[Finding]:
    raw_cookies = result.headers.get_list("set-cookie")
    if not raw_cookies:
        return []
    missing_secure: list[str] = []
    missing_httponly: list[str] = []
    missing_samesite: list[str] = []
    for raw in raw_cookies:
        name, flags, attrs = _parse_cookie(raw)
        label = _truncate(name or "(unnamed)", 60)  # cookie values are never read or stored
        if result.final_scheme == "https" and "secure" not in flags:
            missing_secure.append(label)
        if "httponly" not in flags:
            missing_httponly.append(label)
        if "samesite" not in attrs:
            missing_samesite.append(label)
    findings: list[Finding] = []
    if missing_secure:
        findings.append(
            Finding(
                id="SS-COOKIE-SECURE-001",
                title="Cookies set without the Secure attribute",
                severity=Severity.MEDIUM,
                category="Cookies",
                description="Cookies without Secure can be sent over unencrypted connections.",
                evidence="Cookie names: " + ", ".join(sorted(set(missing_secure))),
                remediation="Add the Secure attribute to every cookie on HTTPS sites.",
            )
        )
    if missing_httponly:
        findings.append(
            Finding(
                id="SS-COOKIE-HTTPONLY-001",
                title="Cookies set without the HttpOnly attribute",
                severity=Severity.LOW,
                category="Cookies",
                description=(
                    "Cookies without HttpOnly are readable by scripts, so a cross-site scripting "
                    "flaw could steal them. This matters most for session cookies."
                ),
                evidence="Cookie names: " + ", ".join(sorted(set(missing_httponly))),
                remediation="Add HttpOnly to cookies that scripts do not need to read, especially session cookies.",
            )
        )
    if missing_samesite:
        findings.append(
            Finding(
                id="SS-COOKIE-SAMESITE-001",
                title="Cookies set without an explicit SameSite attribute",
                severity=Severity.LOW,
                category="Cookies",
                description="Without SameSite, behavior depends on the browser default, which weakens cross-site request protection.",
                evidence="Cookie names: " + ", ".join(sorted(set(missing_samesite))),
                remediation="Set SameSite=Lax (or Strict) explicitly; use None only with Secure when truly required.",
            )
        )
    return findings


def check_directory_index(result: FetchResult) -> list[Finding]:
    if result.headers.get("content-encoding"):
        return []  # compressed body is not inspected
    content_type = (result.headers.get("content-type") or "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return []
    text = result.body_sample.decode("utf-8", errors="replace")
    for signature in DIRECTORY_INDEX_SIGNATURES:
        if signature.search(text):
            return [
                Finding(
                    id="SS-DIR-001",
                    title="Directory listing appears to be enabled",
                    severity=Severity.MEDIUM,
                    category="Information disclosure",
                    description="The page looks like an automatically generated directory index, which can expose files that were never meant to be public.",
                    evidence="Response contains a directory-index signature (page body is not stored).",
                    remediation="Disable directory indexing in the web server (e.g. 'autoindex off' in nginx, 'Options -Indexes' in Apache).",
                )
            ]
    return []


def check_off_origin_redirect(result: FetchResult) -> list[Finding]:
    if not result.off_origin_redirect:
        return []
    return [
        Finding(
            id="SS-SCOPE-001",
            title="Scan stopped at a redirect to a different site",
            severity=Severity.INFO,
            category="Scan scope",
            description=(
                "The target redirected to another site. SecureScope does not follow redirects "
                "to other sites because you only confirmed authorization for the original target."
            ),
            evidence=f"Redirect destination: {result.off_origin_redirect}",
            remediation="Scan the destination directly if you are authorized to test it.",
        )
    ]


Check = Callable[[FetchResult], list[Finding]]

CHECKS: tuple[tuple[str, Check], ...] = (
    ("https", check_https),
    ("hsts", check_hsts),
    ("csp", check_csp),
    ("x-content-type-options", check_content_type_options),
    ("referrer-policy", check_referrer_policy),
    ("permissions-policy", check_permissions_policy),
    ("disclosure-headers", check_disclosure_headers),
    ("cookie-attributes", check_cookies),
    ("directory-index", check_directory_index),
    ("scan-scope", check_off_origin_redirect),
)


def run_checks(result: FetchResult) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    names: list[str] = []
    for name, check in CHECKS:
        names.append(name)
        findings.extend(check(result))
    return findings, names
