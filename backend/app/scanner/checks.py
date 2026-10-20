"""Passive checks. Pure functions: response metadata in, findings out.

Nothing here sends traffic. Checks are deliberately limited and conservative; they look at the
single response the fetcher already obtained.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.scanner.fetcher import FetchResult, ProbeResponse
from app.scanner.tls import TlsObservation
from app.schemas.scan import Confidence, Finding, Severity, SkippedCheck, TlsSummary

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


SECURITY_HEADERS: tuple[str, ...] = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)


def observed_context(result: FetchResult) -> str:
    """Describe exactly what was looked at, so a "missing" finding can be checked by the reader."""
    present = [
        f"{name}: {_truncate(result.headers[name], 80)}"
        for name in SECURITY_HEADERS
        if name in result.headers
    ]
    seen = "; ".join(present) if present else "none of the common security headers"
    return f"Checked the HTTP {result.status_code} response from {result.final_url}. Security headers seen: {seen}."


def _missing(result: FetchResult, header: str) -> str:
    return f"{header} was not present. {observed_context(result)}"


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
                evidence=_missing(result, "Strict-Transport-Security"),
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
                evidence=_missing(result, "Content-Security-Policy"),
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
            evidence=(
                _missing(result, "X-Content-Type-Options")
                if not value
                else f"X-Content-Type-Options was '{_truncate(value)}', expected 'nosniff'. {observed_context(result)}"
            ),
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
            evidence=_missing(result, "Referrer-Policy"),
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
            evidence=_missing(result, "Permissions-Policy"),
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


# Informational findings from these checks still mean the check did not pass.
NOT_PASSED_AT_INFO: tuple[str, ...] = ("SS-DISC-SEC-",)

# Paths requested once each, in addition to the page itself. Fixed here, never taken from user input.
PROBE_PATHS: tuple[str, ...] = ("/.well-known/security.txt", "/.git/HEAD", "/.env")
ENV_LINE = re.compile(rb"^[ \t]*(?:export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=", re.MULTILINE)
GIT_HEAD = re.compile(rb"^ref: refs/[A-Za-z0-9._/-]+\s*$|^[0-9a-f]{40}\s*$")


def _is_html(response: ProbeResponse) -> bool:
    kind = (response.content_type or "").lower()
    return "html" in kind or response.body_sample.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))


def probes_conclusive(probes: dict[str, ProbeResponse], path: str) -> bool:
    """Whether the probe gave an answer we can reason about (a 5xx or a transport error does not)."""
    response = probes.get(path)
    return response is not None and response.error is None and response.status is not None and (
        response.status < 500 and response.status != 429
    )


def check_exposed_files(result: FetchResult, probes: dict[str, ProbeResponse]) -> list[Finding]:
    """Looks for sensitive files that should never be public. Matches on content signatures, so a site that
    answers every path with its home page (a single-page app) does not trigger a false report. The file
    content is never stored: evidence says only what was recognised."""
    found: list[Finding] = []
    git = probes.get("/.git/HEAD")
    if git and git.status == 200 and not _is_html(git) and GIT_HEAD.match(git.body_sample.strip()[:200]):
        found.append(
            Finding(
                id="SS-EXPOSE-GIT-001",
                title="Git repository metadata is publicly readable",
                severity=Severity.HIGH,
                category="Exposed files",
                description=(
                    "The site serves /.git/HEAD. When a .git directory is readable, an attacker can usually "
                    "download the whole repository, including source code and any secrets committed to its "
                    "history."
                ),
                evidence=(
                    f"GET {result.final_scheme}://{result.host}/.git/HEAD returned HTTP 200 with content "
                    "in the format of a Git HEAD file. The content itself was not stored."
                ),
                remediation=(
                    "Remove the .git directory from the web root or block all dot-directories at the web "
                    "server or CDN. Treat any secret that was ever committed as exposed and rotate it."
                ),
            )
        )
    env = probes.get("/.env")
    if env and env.status == 200 and not _is_html(env):
        lines = len(ENV_LINE.findall(env.body_sample))
        if lines >= 2:
            found.append(
                Finding(
                    id="SS-EXPOSE-ENV-001",
                    title="An environment file appears to be publicly readable",
                    severity=Severity.HIGH,
                    category="Exposed files",
                    description=(
                        "The site serves /.env with content that looks like KEY=VALUE settings. Environment "
                        "files typically hold database passwords and API keys."
                    ),
                    evidence=(
                        f"GET {result.final_scheme}://{result.host}/.env returned HTTP 200 with "
                        f"{lines} lines shaped like KEY=VALUE. Names and values were not stored."
                    ),
                    remediation=(
                        "Remove the file from the web root or deny access to it, then rotate every secret "
                        "it contained, because it may already have been read."
                    ),
                    confidence=Confidence.MEDIUM,
                )
            )
    return found


def check_security_txt(result: FetchResult, probes: dict[str, ProbeResponse]) -> list[Finding]:
    response = probes.get("/.well-known/security.txt")
    if response is None:
        return []
    if (
        response.status == 200
        and not _is_html(response)
        and re.search(rb"^contact:", response.body_sample, re.IGNORECASE | re.MULTILINE)
    ):
        return []
    state = f"HTTP {response.status}" if response.status is not None else "no usable response"
    return [
        Finding(
            id="SS-DISC-SEC-001",
            title="No security.txt contact file",
            severity=Severity.INFO,
            category="Security hygiene",
            description=(
                "A security.txt file (RFC 9116) tells researchers how to report a vulnerability to you. "
                "Without one, reports may not reach the right person."
            ),
            evidence=(
                f"GET {result.final_scheme}://{result.host}/.well-known/security.txt returned {state} "
                "without a valid Contact field."
            ),
            remediation=(
                "Publish /.well-known/security.txt with at least a Contact line and an Expires date, for "
                "example: Contact: mailto:security@your-domain"
            ),
        )
    ]


CERT_SOON_HIGH_DAYS = 14
CERT_SOON_MEDIUM_DAYS = 30

_CERT_FAILURES: dict[str, tuple[str, str, str, str]] = {
    "expired": (
        "SS-TLS-CERT-002",
        "TLS certificate has expired",
        "Browsers show a full-page warning for an expired certificate and many visitors will leave; "
        "API clients usually refuse to connect at all.",
        "Renew the certificate now and enable automatic renewal (for example through your host or an ACME "
        "client). Confirm the new certificate is installed on every server and CDN edge.",
    ),
    "not_yet_valid": (
        "SS-TLS-CERT-005",
        "TLS certificate is not valid yet",
        "The certificate's start date is in the future as seen by the scanner, so clients may reject it.",
        "Check the certificate's validity dates and the clock on the server that issued or serves it.",
    ),
    "hostname_mismatch": (
        "SS-TLS-CERT-003",
        "TLS certificate does not match the host name",
        "The certificate presented was issued for a different name, so browsers warn visitors and cannot "
        "tell this server apart from an impostor.",
        "Install a certificate that lists this exact host name (or a matching wildcard) and check that the "
        "right certificate is served for this name on every edge.",
    ),
    "untrusted": (
        "SS-TLS-CERT-004",
        "TLS certificate is not trusted",
        "The certificate is self-signed or its issuer is not in the standard trust store, so browsers warn "
        "visitors.",
        "Use a certificate from a public certificate authority and make sure the server sends the full "
        "intermediate chain.",
    ),
    "other": (
        "SS-TLS-CERT-005",
        "TLS certificate could not be verified",
        "Standard certificate verification failed for a reason other than expiry, host name or issuer.",
        "Inspect the certificate chain with a TLS checker and reissue the certificate if needed.",
    ),
}


def check_tls_certificate(result: FetchResult, tls: TlsObservation | None) -> list[Finding]:
    """Findings from the one verified TLS connection. Expects a conclusive observation."""
    if tls is None:
        return []
    if tls.outcome == "verification_failed" and tls.failure_kind is not None:
        fid, title, why, fix = _CERT_FAILURES[tls.failure_kind]
        return [
            Finding(
                id=fid,
                title=title,
                severity=Severity.HIGH,
                category="Transport security",
                description=why,
                evidence=f"Certificate verification for {result.host} failed: {tls.detail}",
                remediation=fix,
            )
        ]
    if tls.outcome != "ok":
        return []
    days = tls.days_remaining()
    if days is not None and days <= CERT_SOON_MEDIUM_DAYS:
        severity = Severity.HIGH if days <= CERT_SOON_HIGH_DAYS else Severity.MEDIUM
        until = f"{tls.not_after:%Y-%m-%d}" if tls.not_after else "unknown"
        return [
            Finding(
                id="SS-TLS-CERT-001",
                title="TLS certificate expires soon",
                severity=severity,
                category="Transport security",
                description=(
                    "When the certificate expires, browsers will block the site with a warning. "
                    "Certificates are normally renewed automatically well before this point."
                ),
                evidence=f"The certificate for {result.host} is valid until {until} ({days} days left).",
                remediation=(
                    "Renew the certificate and check that automatic renewal works (for example certbot or "
                    "your host's managed certificates)."
                ),
            )
        ]
    return []


def tls_summary(tls: TlsObservation | None) -> TlsSummary | None:
    if tls is None or tls.outcome not in ("ok", "verification_failed"):
        return None
    return TlsSummary(
        protocol=tls.protocol,
        cipher=tls.cipher,
        not_before=tls.not_before,
        not_after=tls.not_after,
        days_remaining=tls.days_remaining(),
        issuer=tls.issuer,
        subject=tls.subject,
        verified=tls.outcome == "ok",
    )


# Which finding-id prefixes belong to which check, so reports can list checks that found nothing.
CHECK_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {
    "https": ("The page was served over HTTPS", ("SS-TLS-0",)),
    "exposed-files": ("No exposed .git directory or .env file", ("SS-EXPOSE-",)),
    "security-txt": ("A security.txt contact file is published", ("SS-DISC-SEC-",)),
    "tls-certificate": (
        "TLS certificate is valid for this host and not close to expiry",
        ("SS-TLS-CERT-",),
    ),
    "hsts": ("Strict-Transport-Security is set with a long max-age", ("SS-HDR-HSTS-",)),
    "csp": ("Content-Security-Policy is set without unsafe script sources", ("SS-HDR-CSP-",)),
    "x-content-type-options": ("X-Content-Type-Options is nosniff", ("SS-HDR-XCTO-",)),
    "referrer-policy": ("Referrer-Policy is set", ("SS-HDR-REF-",)),
    "permissions-policy": ("Permissions-Policy is set", ("SS-HDR-PERM-",)),
    "disclosure-headers": (
        "No software version shown in the Server or X-Powered-By headers",
        ("SS-DISC-SRV-", "SS-DISC-XPB-"),
    ),
    "cookie-attributes": (
        "No cookie attribute problems found (a site that sets no cookies passes this)",
        ("SS-COOKIE-",),
    ),
    "directory-index": ("No directory listing in the page", ("SS-DIR-",)),
    "scan-scope": ("Scan stayed on the verified site", ("SS-SCOPE-",)),
}

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


# Checks that match page markup or other signals instead of reading a header directly.
HEURISTIC_FINDINGS: frozenset[str] = frozenset({"SS-DIR-001"})


@dataclass
class Assessment:
    findings: list[Finding]
    checks_run: list[str]
    checks_skipped: list[SkippedCheck] = field(default_factory=list)
    tls: TlsSummary | None = None

    @property
    def unverified_prefixes(self) -> tuple[str, ...]:
        """Finding-id prefixes of checks that did not run; their old findings must not be resolved."""
        return tuple(
            p for skipped in self.checks_skipped for p in CHECK_LABELS.get(skipped.name, ("", ()))[1]
        )


def assess(
    result: FetchResult,
    tls: TlsObservation | None = None,
    probes: dict[str, ProbeResponse] | None = None,
) -> Assessment:
    """All passive checks. Checks that need extra observations run only when those are conclusive."""
    findings, names = run_checks(result)
    skipped: list[SkippedCheck] = []
    if probes is not None:
        for name, path, check in (
            ("exposed-files", "/.git/HEAD", check_exposed_files),
            ("security-txt", "/.well-known/security.txt", check_security_txt),
        ):
            needed = ("/.git/HEAD", "/.env") if name == "exposed-files" else (path,)
            if all(probes_conclusive(probes, p) for p in needed):
                names.append(name)
                findings.extend(check(result, probes))
            else:
                skipped.append(
                    SkippedCheck(name=name, reason="The site did not give a usable answer for the probe.")
                )
    if result.final_scheme != "https":
        skipped.append(
            SkippedCheck(
                name="tls-certificate",
                reason="The site was served over HTTP, so there was no certificate to check.",
            )
        )
    elif tls is None:
        skipped.append(SkippedCheck(name="tls-certificate", reason="The TLS check did not run."))
    elif tls.outcome in ("ok", "verification_failed"):
        names.append("tls-certificate")
        findings.extend(check_tls_certificate(result, tls))
    else:
        skipped.append(SkippedCheck(name="tls-certificate", reason=tls.detail or "The TLS check failed."))
    return Assessment(findings, names, skipped, tls_summary(tls))


def run_checks(result: FetchResult) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    names: list[str] = []
    for name, check in CHECKS:
        names.append(name)
        for finding in check(result):
            if finding.id in HEURISTIC_FINDINGS:
                finding = finding.model_copy(update={"confidence": Confidence.MEDIUM})
            findings.append(finding)
    return findings, names
