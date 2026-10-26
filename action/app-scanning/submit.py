#!/usr/bin/env python3
"""SecureScope App Scanning for CI: turns SARIF files into a submission and sends it. Standard library only.

Exit codes: 0 the rules you set were met; 1 they were not, or a check did not run (the result is incomplete);
2 nothing could be submitted, the answer was unusable, or the input could not be understood. An unexpected error
also ends with 2 and a fixed message: a Python traceback would exit with 1, which means "findings", and could
quote input.

Safety rules, each covered by a test:
- the token comes from the environment, is masked and is never printed or put in a URL;
- for secret findings only the rule, the file and the line are sent: never the message, the snippet or the match;
- no source code is read or sent; only the SARIF fields rule, level, file path, line and a short message;
- text from the tools is cleaned before it is printed, so it cannot start a workflow command ("::...");
- the request is never redirected to another host, and the API address must be https (or localhost);
- a retry of the same pipeline run sends the same Idempotency-Key and costs nothing;
- only a clear, complete answer from the server can pass the job: an empty, unexpected or error-like answer never does.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_SARIF_BYTES = 20 * 1024 * 1024
MAX_FINDINGS = 5000  # the server's limit
MAX_RESULTS_READ = 200_000  # results looked at per file; the rest are counted as left out
MAX_BODY_BYTES = 4 * 1024 * 1024 - 16 * 1024  # the server refuses 4 MiB; leave room
MAX_ANSWER_BYTES = 5 * 1024 * 1024
PASSING_RESULTS = ("completed_no_findings", "completed_findings")
SEVERITIES = ("critical", "high", "medium", "low", "info")
RANK = {s: i for i, s in enumerate(SEVERITIES)}  # lower is worse
FAIL_ON = ("critical", "high", "medium", "low", "none")
_SAFE_RULE = re.compile(r"[^A-Za-z0-9._:/-]")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ +-]")
_SAFE_VERSION = re.compile(r"[^A-Za-z0-9._+-]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{8,200}")
DEFAULT_API_URL = "https://getsecurescope.com/api/v1"


class Stop(Exception):
    """A problem to report in one line, with the exit code to use."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def clean(text: object, limit: int = 300) -> str:
    """Safe to write to the log: no control characters and no workflow-command start."""
    return _CONTROL.sub(" ", str(text)).replace("::", ": :")[:limit]


def _d(value: object) -> dict[str, Any]:
    """Anything that is not an object counts as an empty one, so malformed SARIF cannot raise."""
    return value if isinstance(value, dict) else {}


def _l(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def severity_of(result: dict[str, Any], rule: dict[str, Any]) -> str:
    """A numeric security-severity (CVSS-like) wins over the SARIF level."""
    for source in (_d(result.get("properties")), _d(rule.get("properties"))):
        value = source.get("security-severity")
        try:
            score = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            continue
        if score != score:  # NaN
            continue
        if score >= 9.0:
            return "critical"
        if score >= 7.0:
            return "high"
        if score >= 4.0:
            return "medium"
        if score > 0:
            return "low"
        return "info"
    level = result.get("level") or _d(rule.get("defaultConfiguration")).get("level") or "warning"
    return {"error": "high", "warning": "medium", "note": "low", "none": "info"}.get(str(level), "medium")


def safe_path(uri: object) -> str | None:
    if not isinstance(uri, str) or not uri:
        return None
    path = urllib.parse.unquote(uri)
    if path.startswith("file://"):
        path = path[7:]
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    parts = path.split("/")
    if _CONTROL.search(path) or path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in parts:
        return None
    path = "/".join(p for p in parts if p not in ("", "."))
    return path[:255] or None


class Converted:
    """What one SARIF file produced."""

    def __init__(self) -> None:
        self.tool: dict[str, str] = {"name": "unknown", "version": ""}
        self.findings: list[dict[str, Any]] = []
        self.unusable = 0  # no usable rule or path
        self.suppressed = 0  # marked as suppressed in the tool's own output
        self.left_out = 0  # beyond the number of results read
        self.failed_reason = ""  # the tool says it did not run to the end


def convert(document: Any, kind: str) -> Converted:
    """Reads only: rule id, level or score, file, line, and for static analysis a short message and title."""
    runs = [r for r in _l(_d(document).get("runs")) if isinstance(r, dict)]
    if not runs:
        raise Stop("a SARIF file has no run, so it does not show that the tool ran.")
    out = Converted()
    seen = 0
    for index, run in enumerate(runs):
        driver = _d(_d(run.get("tool")).get("driver"))
        if index == 0:
            name = _SAFE_NAME.sub("", str(driver.get("name") or "")).strip()[:64]
            version = _SAFE_VERSION.sub("", str(driver.get("semanticVersion") or driver.get("version") or ""))
            out.tool = {"name": name or "unknown", "version": version[:32]}
        for invocation in _l(run.get("invocations")):
            if _d(invocation).get("executionSuccessful") is False:
                out.failed_reason = "The tool reported that it did not finish successfully."
        rules = {str(r.get("id")): r for r in _l(driver.get("rules")) if isinstance(r, dict) and r.get("id")}
        for result in _l(run.get("results")):
            seen += 1
            if seen > MAX_RESULTS_READ:
                out.left_out += 1
                continue
            result = _d(result)
            rule_id = _SAFE_RULE.sub("_", str(result.get("ruleId") or ""))[:128]
            physical = _d(_d((_l(result.get("locations")) or [{}])[0]).get("physicalLocation"))
            path = safe_path(_d(physical.get("artifactLocation")).get("uri"))
            if not rule_id or path is None:
                out.unusable += 1
                continue
            if _l(result.get("suppressions")):
                out.suppressed += 1
                continue
            rule = _d(rules.get(str(result.get("ruleId"))))
            line = _d(physical.get("region")).get("startLine")
            severity = severity_of(result, rule)
            if kind == "secrets" and RANK[severity] > RANK["high"]:
                # Gitleaks writes no level at all, which would read as medium. A hardcoded secret is never
                # below high, so a pipeline with fail-on high cannot let one through.
                severity = "high"
            finding: dict[str, Any] = {
                "kind": kind,
                "rule_id": rule_id,
                "severity": severity,
                "confidence": "medium",
                "path": path,
            }
            if isinstance(line, int) and not isinstance(line, bool) and 1 <= line <= 10_000_000:
                finding["line"] = line
            if kind == "sast":
                text = _d(result.get("message")).get("text") or ""
                short = _d(rule.get("shortDescription")).get("text") or ""
                finding["title"] = _CONTROL.sub(" ", str(short))[:200]
                finding["message"] = _CONTROL.sub(" ", str(text))[:1000]
            # For secrets nothing else is sent: not the message, the snippet, the match or the commit.
            out.findings.append(finding)
    return out


def load(path: str) -> Any:
    """None when there is no file; Stop when it cannot be read as JSON within the limits."""
    try:
        if not os.path.exists(path):
            return None
        if not os.path.isfile(path):
            raise Stop(f"'{clean(path, 80)}' is not a regular file.")
        if os.path.getsize(path) > MAX_SARIF_BYTES:
            raise Stop(f"the SARIF file '{clean(path, 80)}' is larger than 20 MiB.")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Stop:
        raise
    except (OSError, ValueError, RecursionError, MemoryError) as exc:
        raise Stop(f"the SARIF file '{clean(path, 80)}' could not be read ({type(exc).__name__}).") from None


def skipped(kind: str, reason: str) -> dict[str, Any]:
    return {"kind": kind, "status": "skipped", "reason": reason, "tool": {"name": "unknown"}}


def build(project_id: str, sast_path: str, secrets_path: str, ref: str) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for kind, path in (("sast", sast_path), ("secrets", secrets_path)):
        if not path:
            continue
        document = load(path)
        if document is None:
            checks.append(skipped(kind, "No SARIF file was found at the given path."))
            notes.append(f"No file at '{clean(path, 80)}': the {kind} check is reported as skipped.")
            continue
        try:
            converted = convert(document, kind)
        except Stop as stop:
            checks.append(skipped(kind, "The SARIF file did not show that the tool ran."))
            notes.append(
                f"The {kind} file '{clean(path, 80)}': {clean(stop, 160)} The check is reported as skipped."
            )
            continue
        if converted.failed_reason:
            checks.append(skipped(kind, converted.failed_reason))
            notes.append(f"The {kind} tool did not finish successfully: the check is reported as skipped.")
            continue
        checks.append({"kind": kind, "status": "ran", "tool": converted.tool})
        findings.extend(converted.findings)
        if converted.unusable:
            notes.append(
                f"{converted.unusable} {kind} result(s) had no usable rule or file path and were left out."
            )
        if converted.suppressed:
            notes.append(
                f"{converted.suppressed} {kind} result(s) marked as suppressed by the tool were left out."
            )
        if converted.left_out:
            notes.append(
                f"{converted.left_out} {kind} result(s) beyond the first {MAX_RESULTS_READ} were left out."
            )
    if not checks:
        raise Stop("give at least one of sast-sarif and secrets-sarif.")
    if len(findings) > MAX_FINDINGS:
        findings.sort(key=lambda f: RANK[f["severity"]])
        notes.append(
            f"{len(findings) - MAX_FINDINGS} lower-severity findings were left out (limit {MAX_FINDINGS})."
        )
        findings = findings[:MAX_FINDINGS]
    document = {"schema_version": 1, "project_id": project_id, "checks": checks, "findings": findings}
    if ref:
        document["ref"] = ref
    return document, notes


def encode(document: dict[str, Any], notes: list[str]) -> bytes:
    """The server refuses more than 4 MiB. Shorten messages first, then drop the least severe findings."""
    body = json.dumps(document, separators=(",", ":")).encode()
    if len(body) <= MAX_BODY_BYTES:
        return body
    for finding in document["findings"]:
        if "message" in finding:
            finding["message"] = finding["message"][:200]
    body = json.dumps(document, separators=(",", ":")).encode()
    if len(body) > MAX_BODY_BYTES:
        findings = sorted(document["findings"], key=lambda f: RANK[f["severity"]])
        low, high = 0, len(findings)
        while low < high:  # the largest number of findings that fits
            middle = (low + high + 1) // 2
            document["findings"] = findings[:middle]
            if len(json.dumps(document, separators=(",", ":")).encode()) <= MAX_BODY_BYTES:
                low = middle
            else:
                high = middle - 1
        notes.append(
            f"{len(findings) - low} lower-severity findings were left out to stay under the 4 MiB limit."
        )
        document["findings"] = findings[:low]
        body = json.dumps(document, separators=(",", ":")).encode()
    notes.append("Long messages were shortened to stay under the 4 MiB limit.")
    return body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def post(url: str, token: str, key: str, body: bytes) -> tuple[int, dict[str, Any], str]:
    """One request. Status 0 means no usable answer (connection problem, timeout, bad address)."""
    if not url.startswith(("https://", "http://")):  # never file: or another scheme
        return 0, {}, ""
    request = urllib.request.Request(  # noqa: S310  (scheme checked just above)
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": key,
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=60) as response:  # noqa: S310
            raw, status, retry = response.read(MAX_ANSWER_BYTES), response.status, ""
    except urllib.error.HTTPError as exc:
        raw, status, retry = exc.read(MAX_ANSWER_BYTES), exc.code, exc.headers.get("Retry-After", "")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}, ""
    try:
        parsed = json.loads(raw)
    except (ValueError, RecursionError):
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}, retry


def submit(
    api_url: str, token: str, key: str, body: bytes, sleep: Any = time.sleep
) -> tuple[int, dict[str, Any]]:
    """A sleeping free-tier backend needs about a minute to wake, and a busy one answers 503 with Retry-After.
    A retry after a timeout is safe: the same Idempotency-Key returns the run the first attempt made."""
    status = 0
    parsed: dict[str, Any] = {}
    for attempt in range(8):
        status, parsed, retry = post(f"{api_url}/app/ci/submissions", token, key, body)
        if status not in (0, 502, 503, 504):
            return status, parsed
        wait = min(int(retry), 60) if retry.isdigit() else 15
        print(f"SecureScope did not answer yet (attempt {attempt + 1}). Waiting {wait} s...", file=sys.stderr)
        if attempt < 7:
            sleep(wait)
    return status, parsed


def explain(status: int, body: dict[str, Any]) -> str:
    detail = body.get("detail")
    if isinstance(detail, dict):
        detail = detail.get("message")
    detail = clean(detail or "", 200) if isinstance(detail, str) else ""
    known = {
        0: "no answer after eight attempts (server not reachable).",
        400: "the request was refused.",
        401: "the token was refused (wrong, revoked, expired, or not an App Scanning token on a plan that includes it).",
        403: "the monthly allowance of this plan is used up.",
        404: "the project was not found in the workspace of this token.",
        409: "this Idempotency-Key was used for a different project.",
        413: "the results are larger than 4 MiB.",
        422: "the results were refused.",
        429: "too many submissions in the last hour. Try again later.",
    }
    return f"SecureScope answered {status}: {known.get(status, 'the submission failed.')} {detail}".strip()


def evaluate(answer: dict[str, Any], fail_on: str) -> tuple[bool, list[str]]:
    """Only a clearly completed run can pass. Anything else (incomplete, scanner error, interrupted, an
    unknown label) fails the job."""
    raw_counts = answer.get("counts")
    counts: dict[str, Any] = raw_counts if isinstance(raw_counts, dict) else {}
    lines: list[str] = []
    passed = True
    if fail_on != "none":
        for severity in SEVERITIES[: RANK[fail_on] + 1]:
            n = counts.get(severity, 0)
            if isinstance(n, int) and n > 0:
                passed = False
                lines.append(f"{n} {severity} finding(s)")
    if answer.get("result") == "incomplete":
        passed = False
        lines.append("a check did not run, so the result is incomplete")
    elif answer.get("result") not in PASSING_RESULTS:
        passed = False
        lines.append(f"the run did not complete ({clean(answer.get('result', 'no result'), 40)})")
    return passed, lines


def check_settings(env: dict[str, str]) -> tuple[str, str, str, str]:
    """Returns (token, project_id, fail_on, api_url) or raises Stop. Nothing is sent before this passes."""
    token = env.get("SS_API_KEY", "")
    if not token:
        raise Stop("no API token was given (input api-key).")
    if not _TOKEN.fullmatch(token):
        raise Stop("the API token is not in the expected form.")
    if token.startswith("ssk_"):
        raise Stop("this is a Web Scanning token. App Scanning needs a token with scope 'app'.")
    print(f"::add-mask::{token}")
    project_id = env.get("SS_PROJECT_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9]{1,64}", project_id):
        raise Stop("project-id is missing or not valid.")
    fail_on = env.get("SS_FAIL_ON", "high") or "high"
    if fail_on not in FAIL_ON:
        raise Stop("fail-on must be critical, high, medium, low or none.")
    api_url = (env.get("SS_API_URL") or DEFAULT_API_URL).rstrip("/")
    parts = urllib.parse.urlsplit(api_url)
    local = parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")
    if (
        (parts.scheme != "https" and not local)
        or not parts.hostname
        or _CONTROL.search(api_url)
        or " " in api_url
    ):
        raise Stop("the api-url must start with https://.")
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise Stop("the api-url must not contain a user name, password, query or fragment.")
    if not local and api_url != DEFAULT_API_URL:
        print(
            f"::warning::SecureScope: the token will be sent to {clean(parts.hostname, 100)}, not the default address."
        )
    return token, project_id, fail_on, api_url


def main(env: dict[str, str] | None = None, sleep: Any = time.sleep) -> int:
    env = dict(os.environ) if env is None else env
    try:
        return run(env, sleep)
    except Stop as stop:
        print(f"::error::SecureScope: {clean(stop)}")
        return stop.code
    except Exception as exc:  # a defect must not look like "findings found" (a traceback exits with 1)
        print(
            f"::error::SecureScope: unexpected error ({type(exc).__name__}). Nothing was submitted or the answer was not understood."
        )
        return 2


def run(env: dict[str, str], sleep: Any) -> int:
    token, project_id, fail_on, api_url = check_settings(env)
    sha = env.get("GITHUB_SHA", "")[:12]
    ref = clean(f"{env.get('GITHUB_REF_NAME', '')}@{sha}".strip("@"), 120)
    document, notes = build(project_id, env.get("SS_SAST_SARIF", ""), env.get("SS_SECRETS_SARIF", ""), ref)
    body = encode(document, notes)
    digest = hashlib.sha256(body).hexdigest()[:16]
    key = f"gh-{env.get('GITHUB_RUN_ID', 'local')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}-{digest}"
    key = re.sub(r"[^A-Za-z0-9._:-]", "_", key)[:70]
    for note in notes:
        print(f"::warning::SecureScope: {clean(note)}")
    status, answer = submit(api_url, token, key, body, sleep)
    if status != 201:
        raise Stop(explain(status, answer))
    scan_id = answer.get("id")
    if (
        not isinstance(scan_id, str)
        or not re.fullmatch(r"[A-Za-z0-9]{1,64}", scan_id)
        or not isinstance(answer.get("result"), str)
    ):
        raise Stop(
            "the answer of the server was not what a submission returns, so nothing can be said about the result."
        )
    passed, reasons = evaluate(answer, fail_on)
    result = clean(answer["result"], 40)
    print(f"SecureScope run {scan_id}: {clean(answer.get('result_text', result))}")
    if answer.get("replayed"):
        print(
            "This pipeline run was already submitted; the earlier run is shown and nothing was counted again."
        )
    outputs = env.get("GITHUB_OUTPUT")
    if outputs:
        with open(outputs, "a", encoding="utf-8") as handle:
            handle.write(f"scan-id={scan_id}\nresult={result}\npassed={str(passed).lower()}\n")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(
                f"### SecureScope App Scanning\n\nResult: `{result}`. Passed: `{str(passed).lower()}`.\n"
            )
    if not passed:
        print(f"::error::SecureScope: the rules were not met: {'; '.join(reasons)}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
