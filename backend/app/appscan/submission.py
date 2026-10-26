"""Results of tools the customer ran on their own runner (static analysis, secret detection), checked and normalised.

The server never sees source code. It receives a small JSON document and treats it as hostile:
- the schema is strict: unknown fields, wrong types, out-of-range values and oversized lists are refused;
- anything that looks like a secret anywhere in the document refuses the whole submission, with a fixed message
  that does not repeat the content (the customer must remove it and rerun);
- text from the tool is cleaned and capped; for secret findings the submitter's text is dropped altogether and
  fixed wording is used, so no value (or part of one) can be stored;
- the server cannot verify that a tool really ran, so every scanner entry is labelled as reported by the
  submitter and a submission with no completed check is never shown as complete.

Nothing here opens a network connection or starts a process."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.appscan.pipeline import MAX_FINDINGS, CodeFinding, ScanOutcome, _text
from app.appscan.redaction import SecretRejected, reject_if_secret
from app.appscan.states import AppScanStatus
from app.schemas.scan import Confidence, Severity

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_CHECKS = 20
# Strings, keys and containers in one document. A full submission (5,000 findings of eight fields) is about
# 85,000; more than this is refused before the secret check, which costs time for every string it reads.
MAX_NODES = 100_000
_SAFE_RULE = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._ +-]{1,64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

EXPOSED_TITLE = "Possible hardcoded secret"
EXPOSED_DESCRIPTION = (
    "A secret scanner running in your pipeline reported what looks like a credential at this location. "
    "SecureScope does not receive or keep the value."
)
EXPOSED_REMEDIATION = (
    "Treat the credential as exposed: revoke and rotate it at its provider, remove it from the code and from "
    "version history, and check the provider's logs for misuse. SecureScope never revokes or rotates anything."
)
SAST_REMEDIATION = (
    "Review the code at this location and apply the fix suggested by the rule that reported it. "
    "This result comes from a tool you ran; SecureScope has not read your code."
)


class SubmissionRejected(ValueError):
    """The document was refused. `code` is machine-readable; the message is fixed text and never echoes input."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Tool(_Strict):
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(default="", max_length=32)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not _SAFE_NAME.match(v):
            raise ValueError("name")
        return v

    @field_validator("version")
    @classmethod
    def _version(cls, v: str) -> str:
        if v and not re.match(r"^[A-Za-z0-9._+-]{1,32}$", v):
            raise ValueError("version")
        return v


class Check(_Strict):
    kind: Literal["sast", "secrets"]
    status: Literal["ran", "skipped"]
    reason: str = Field(default="", max_length=200)
    tool: Tool


class SubmittedFinding(_Strict):
    kind: Literal["sast", "secrets"]
    rule_id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: Literal["high", "medium", "low"] = "medium"
    path: str = Field(min_length=1, max_length=255)
    line: int | None = Field(default=None, ge=1, le=10_000_000)
    title: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=1000)

    @field_validator("rule_id")
    @classmethod
    def _rule(cls, v: str) -> str:
        if not _SAFE_RULE.match(v):
            raise ValueError("rule_id")
        return v

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        parts = v.replace("\\", "/").split("/")
        if _CONTROL.search(v) or v.startswith("/") or re.match(r"^[A-Za-z]:", v) or ".." in parts:
            raise ValueError("path")
        return "/".join(p for p in parts if p not in ("", "."))


class Submission(_Strict):
    schema_version: Literal[1]
    project_id: str = Field(pattern=r"^[A-Za-z0-9]{1,64}$")
    ref: str = Field(default="", max_length=120)
    checks: list[Check] = Field(min_length=1, max_length=MAX_CHECKS)
    findings: list[SubmittedFinding] = Field(max_length=MAX_FINDINGS)


def _too_many_nodes(document: Any) -> bool:
    """Counts every value and key without recursion, and stops as soon as the limit is passed."""
    stack = [document]
    count = 0
    while stack:
        item = stack.pop()
        count += 1
        if count > MAX_NODES:
            return True
        if isinstance(item, dict):
            count += len(item)  # the keys
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return count > MAX_NODES


def parse_submission(document: Any) -> Submission:
    """Validates the document. Order matters: the secret check comes first, before anything is interpreted or
    copied, so no later error message can contain it."""
    if _too_many_nodes(document):
        raise SubmissionRejected("too_large", "The submission is too large or too complex.")
    try:
        reject_if_secret(document)
    except SecretRejected as exc:
        raise SubmissionRejected(
            "contains_secret",
            "The submission appears to contain a secret. Nothing was stored. Remove it and run the check again.",
        ) from exc
    except ValueError as exc:
        raise SubmissionRejected("too_deep", "The submission is nested too deeply.") from exc
    if not isinstance(document, dict):
        raise SubmissionRejected("malformed", "The submission is not valid.")
    try:
        return Submission.model_validate(document)
    except ValidationError as exc:
        # Pydantic's messages can quote input; use only the location of the first problem.
        where = ".".join(str(x) for x in exc.errors()[0]["loc"][:3]) if exc.errors() else ""
        where = re.sub(r"[^A-Za-z0-9_.]", "", where)[:60]
        raise SubmissionRejected(
            "invalid", f"The submission is not valid (see field: {where or 'document'})."
        ) from exc


def _fingerprint(project_id: str, kind: str, rule_id: str, path: str, occurrence: int) -> str:
    """Line numbers are not part of it, so a finding that moves down a file is the same finding."""
    return hashlib.sha256(f"app|{kind}|{project_id}|{rule_id}|{path}|{occurrence}".encode()).hexdigest()


def build_outcome(sub: Submission) -> ScanOutcome:
    """Turns a validated submission into the stored result. Status rules: Completed only if every listed check
    ran; Incomplete if any was skipped or no check ran; the server cannot verify that a tool really ran."""
    ran = [c for c in sub.checks if c.status == "ran"]
    skipped = [c for c in sub.checks if c.status == "skipped"]
    outcome = ScanOutcome(status=AppScanStatus.COMPLETED if ran and not skipped else AppScanStatus.INCOMPLETE)
    outcome.checks_run = sorted({c.kind for c in ran})
    outcome.checks_skipped = [
        {"check": c.kind, "reason": _text(c.reason, 200) or "The check did not run."} for c in skipped
    ]
    outcome.scanners = [
        {"name": c.tool.name, "version": c.tool.version, "kind": c.kind, "reported_by": "submitter"}
        for c in ran
    ]
    if not ran:
        outcome.checks_skipped.append({"check": "all", "reason": "No check reported that it ran."})
    ran_kinds = {c.kind for c in ran}
    ordered = sorted(sub.findings, key=lambda f: (f.kind, f.rule_id, f.path, f.line or 0))
    seen: dict[tuple[str, str, str], int] = defaultdict(int)
    for f in ordered:
        if f.kind not in ran_kinds:
            # A finding for a check that did not run is not trusted, and the gap is stated.
            outcome.checks_skipped.append(
                {"check": f.kind, "reason": "Findings were submitted for a check that did not report as run."}
            )
            continue
        key = (f.kind, f.rule_id, f.path)
        seen[key] += 1
        is_secret = f.kind == "secrets"
        message = "" if is_secret else _text(f.message, 1000)
        outcome.findings.append(
            CodeFinding(
                kind=f.kind,
                rule_id=f.rule_id,
                title=EXPOSED_TITLE if is_secret else (_text(f.title, 200) or f"Rule {f.rule_id}"),
                severity=Severity(f.severity),
                confidence=Confidence(f.confidence),
                category="Hardcoded secret" if is_secret else "Code issue",
                description=EXPOSED_DESCRIPTION
                if is_secret
                else (message or f"Rule {f.rule_id} reported an issue at this location."),
                remediation=EXPOSED_REMEDIATION if is_secret else SAST_REMEDIATION,
                path=_text(f.path, 255),
                line=f.line,
                fingerprint=_fingerprint(sub.project_id, f.kind, f.rule_id, f.path, seen[key]),
                evidence=None,
            )
        )
    return outcome
