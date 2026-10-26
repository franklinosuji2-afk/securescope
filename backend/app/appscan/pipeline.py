"""Turns parsed manifests into a scan result: findings, an honest status and the coverage that was achieved.

Status rules (never describe an incomplete scan as clean):
- COMPLETED: every listed package was checked and the source answered for all of them. Findings, if any, do not
  change this.
- INCOMPLETE: anything was not checked: the source did not answer for some packages, entries were unsupported
  (ranges, addresses, options), the time budget ran out, or findings were cut off.
- FAILED: nothing could be checked at all, or no package was found.
Nothing here runs customer code or contacts any service except through the injected source."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.appscan.manifests import Package, ParseResult
from app.appscan.redaction import redact_text
from app.appscan.states import AppScanStatus
from app.appscan.vulns import Advisory, SourceInfo, SourceUnavailable, VulnerabilitySource
from app.schemas.scan import Confidence, Severity

MAX_FINDINGS = 5_000
MAX_SUMMARY_CHARS = 500
MAX_REFERENCES = 5
MAX_FIXED_VERSIONS = 8
DEFAULT_BUDGET_SECONDS = 60.0
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_REFERENCE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,300}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


@dataclass(frozen=True, slots=True)
class DependencyFinding:
    rule_id: str
    title: str
    severity: Severity
    confidence: Confidence
    description: str
    remediation: str
    ecosystem: str
    package_name: str
    package_version: str
    path: str
    fixed_versions: tuple[str, ...]
    references: tuple[str, ...]
    aliases: tuple[str, ...]
    fingerprint: str
    kind: str = "dependency"
    category: str = "Vulnerable dependency"


@dataclass(slots=True)
class ScanOutcome:
    status: AppScanStatus
    findings: list[DependencyFinding] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[dict[str, str]] = field(default_factory=list)
    scanners: list[dict[str, str]] = field(default_factory=list)
    packages_checked: int = 0
    packages_not_answered: int = 0
    entries_unsupported: int = 0
    error: str | None = None


def normalise_severity(raw: str | None) -> tuple[Severity, bool]:
    """(severity, given). A word or a CVSS base score maps to our levels; anything else is MEDIUM with
    given=False so the finding says the source gave none, instead of inventing certainty."""
    if raw:
        text = raw.strip().lower()
        words = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        if text in words:
            return words[text], True
        try:
            score = float(text)
        except ValueError:
            return Severity.MEDIUM, False
        if 0.0 <= score <= 10.0:
            if score >= 9.0:
                return Severity.CRITICAL, True
            if score >= 7.0:
                return Severity.HIGH, True
            if score >= 4.0:
                return Severity.MEDIUM, True
            return (Severity.LOW if score > 0 else Severity.INFO), True
    return Severity.MEDIUM, False


def _text(value: str, limit: int) -> str:
    return redact_text(_CONTROL.sub(" ", value)).strip()[:limit]


def fingerprint(project_id: str, advisory_id: str, ecosystem: str, name: str) -> str:
    """Stable across runs and across package versions, so a finding is recognised after an upgrade that does not
    fix it. Line numbers and versions are not part of it."""
    return hashlib.sha256(
        f"app|dependency|{project_id}|{advisory_id}|{ecosystem}|{name}".encode()
    ).hexdigest()


def _finding(project_id: str, package: Package, advisory: Advisory) -> DependencyFinding | None:
    if not _SAFE_ID.match(advisory.id):
        return None
    severity, given = normalise_severity(advisory.severity)
    fixed = tuple(v for v in advisory.fixed_versions if _SAFE_ID.match(v))[:MAX_FIXED_VERSIONS]
    refs = tuple(r for r in advisory.references if _SAFE_REFERENCE.match(r))[:MAX_REFERENCES]
    aliases = tuple(a for a in advisory.aliases if _SAFE_ID.match(a))[:10]
    summary = _text(advisory.summary, MAX_SUMMARY_CHARS)
    description = (
        f"{package.name} {package.version} is listed in advisory {advisory.id}."
        + (f" The advisory says: {summary}" if summary else "")
        + (
            ""
            if given
            else " The advisory source did not give a severity, so Medium is shown until you check it."
        )
    )
    if fixed:
        remediation = (
            f"Upgrade {package.name} to a fixed version ({', '.join(fixed)}), then test your application. "
            "SecureScope does not change your dependencies."
        )
    else:
        remediation = (
            "The advisory source lists no fixed version. Read the advisory for mitigations or a replacement, "
            "and check whether your use of the package is affected."
        )
    return DependencyFinding(
        rule_id=advisory.id,
        title=f"{package.name} {package.version} has a known vulnerability ({advisory.id})",
        severity=severity,
        confidence=Confidence.HIGH,
        description=description,
        remediation=remediation,
        ecosystem=package.ecosystem,
        package_name=package.name,
        package_version=package.version,
        path=package.source_file,
        fixed_versions=fixed,
        references=refs,
        aliases=aliases,
        fingerprint=fingerprint(project_id, advisory.id, package.ecosystem, package.name),
    )


def run_dependency_scan(
    project_id: str,
    parsed: list[ParseResult],
    source: VulnerabilitySource,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> ScanOutcome:
    outcome = ScanOutcome(status=AppScanStatus.COMPLETED)
    packages: list[Package] = []
    seen: set[tuple[str, str, str]] = set()
    for result in parsed:
        outcome.entries_unsupported += len(result.unsupported) + (1 if result.unsupported_truncated else 0)
        for package in result.packages:
            key = (package.ecosystem, package.name, package.version)
            if key not in seen:
                seen.add(key)
                packages.append(package)
    if outcome.entries_unsupported:
        outcome.checks_skipped.append(
            {
                "check": "dependency",
                "reason": f"{outcome.entries_unsupported} entries could not be checked (ranges, addresses or options).",
            }
        )
    if not packages:
        outcome.status = AppScanStatus.FAILED
        outcome.error = "No checkable packages were found in the files."
        return outcome

    deadline = clock() + budget_seconds
    info: SourceInfo | None = None
    found: dict[tuple[str, str, str, str], DependencyFinding] = {}
    batch_size = max(1, int(source.max_batch))
    for start in range(0, len(packages), batch_size):
        batch = packages[start : start + batch_size]
        if clock() > deadline:
            outcome.packages_not_answered += len(batch)
            continue
        try:
            reply = source.lookup(batch)
        except SourceUnavailable:
            outcome.packages_not_answered += len(batch)
            continue
        except Exception:  # noqa: BLE001  (a broken source must degrade the scan, never crash it or leak its message)
            outcome.packages_not_answered += len(batch)
            continue
        info = reply.info
        if len(reply.advisories) != len(batch):
            outcome.packages_not_answered += len(batch)  # a reply that does not line up is not trusted
            continue
        for package, advisories in zip(batch, reply.advisories, strict=True):
            if advisories is None:
                outcome.packages_not_answered += 1
                continue
            outcome.packages_checked += 1
            for advisory in advisories:
                finding = _finding(project_id, package, advisory)
                if finding is not None:
                    found[(finding.rule_id, package.ecosystem, package.name, package.version)] = finding

    if info is not None:
        outcome.scanners.append(
            {"name": info.name, "version": info.version, "data_timestamp": info.data_timestamp or ""}
        )
    order = {
        s: i
        for i, s in enumerate(
            (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
        )
    }
    findings = sorted(found.values(), key=lambda f: (order[f.severity], f.package_name, f.rule_id))
    if len(findings) > MAX_FINDINGS:
        findings = findings[:MAX_FINDINGS]
        outcome.checks_skipped.append(
            {"check": "dependency", "reason": f"Only the first {MAX_FINDINGS} findings are kept."}
        )
        outcome.status = AppScanStatus.INCOMPLETE
    outcome.findings = findings

    if outcome.packages_not_answered:
        outcome.checks_skipped.append(
            {
                "check": "dependency",
                "reason": f"The vulnerability source gave no answer for {outcome.packages_not_answered} packages.",
            }
        )
    if outcome.packages_checked == 0:
        outcome.status = AppScanStatus.FAILED
        outcome.error = "The vulnerability source could not be reached, so nothing was checked."
        return outcome
    if outcome.packages_not_answered or outcome.entries_unsupported:
        outcome.status = AppScanStatus.INCOMPLETE
    if outcome.packages_checked:
        outcome.checks_run.append("dependency")
    return outcome
