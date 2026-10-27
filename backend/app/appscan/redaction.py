"""The one place that decides which text may be stored, logged or returned by App Scanning.

Rule: no character of a secret is ever kept. A match is replaced as a whole by a marker that names the rule, never
a masked version with some characters left. A secret finding keeps only the rule name, a length class and a keyed
hash for recognising the same finding again.

This is a safety net for common credential shapes plus high-entropy candidates. It does not find every secret, and
it can flag a harmless string. Known blind spots: a secret that is split across lines, a low-entropy password with
no keyword near it, and pure hexadecimal strings of 32, 40 or 64 characters (these look like digests and commit
ids, so they are not treated as secrets on shape alone).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from dataclasses import dataclass
from typing import Any

MARKER = "[REDACTED:{rule}]"
# What callers show when a submission is refused. Fixed text: it never echoes the content that triggered it.
REJECTION_MESSAGE = (
    "The submission contains what looks like a secret and was not stored. Remove it and send again."
)
MAX_TEXT_CHARS = 20_000
MAX_DEPTH = 16

# Token shapes (the same families the repository's own secret scan looks for, plus common extras).
_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key-block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----)?", re.S),
    ),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "github-token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    ),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("google-client-secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{10,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("pypi-token", re.compile(r"\bpypi-[A-Za-z0-9_-]{50,}\b")),
    (
        "provider-secret-key",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b|\bsk-[A-Za-z0-9]{32,}\b"),
    ),
    ("mail-provider-key", re.compile(r"\bxkeysib-[A-Za-z0-9-]{20,}\b|\bre_[A-Za-z0-9]{24,}\b")),
    ("securescope-token", re.compile(r"\b(?:ssk|whsec)_[A-Za-z0-9_-]{40,}\b")),
    ("json-web-token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-credential", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "url-with-credentials",
        re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]{1,20}://[^\s:/@\"'<>]+:[^\s@\"'<>]+@[^\s/\"'<>]+"),
    ),
)
# `password = "value"`, `api_key: value`, `TOKEN=value`. Only the value is replaced; the name stays. Written as a
# keyword search followed by a bounded look-ahead, because one pattern that scans for the name and then the value
# backtracks badly on long strings (found by test_pathological_input_is_fast).
_KEYWORD = re.compile(
    r"(?i)password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|credential|auth"
)
_ASSIGNMENT_TAIL = re.compile(r"[\w.-]{0,40}\s{0,4}(?:=>|=|:)\s{0,4}[\"']?(?P<value>[^\s\"',;]{6,})")
_PLACEHOLDER_VALUE = re.compile(
    r"(?i)^(?:<.*>|\$\{.*\}|\{\{.*\}\}|%.*%|x{4,}|\*{3,}|changeme|change-me|example|your[_-].*|none|null|true|false)$"
)
_CANDIDATE = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
_PURE_HEX = re.compile(r"^[0-9a-fA-F]+$")
_ENTROPY_MIN = 4.0
_LENGTH_MIN = 24


@dataclass(frozen=True, slots=True)
class SecretMatch:
    """Where a secret was found. Deliberately holds no part of the value."""

    rule: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


class SecretRejected(ValueError):
    """A submission was refused because it contains a likely secret. The message never contains the content."""

    def __init__(self) -> None:
        super().__init__(REJECTION_MESSAGE)


def _entropy(text: str) -> float:
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _classes(text: str) -> int:
    return sum(bool(re.search(p, text)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]"))


def _looks_random(token: str) -> bool:
    if len(token) < _LENGTH_MIN or _PURE_HEX.match(token):
        return False
    # Paths and URLs made of words are not secrets: a random token rarely contains the same separator pattern.
    if token.count("/") > 3 or token.count("-") > 4 or token.count("_") > 4:
        return False
    return _classes(token) >= 3 and _entropy(token) >= _ENTROPY_MIN


def find_secrets(text: str) -> list[SecretMatch]:
    """Every likely secret in `text`, as positions only, sorted and non-overlapping."""
    text = text[:MAX_TEXT_CHARS]
    found: list[SecretMatch] = []
    for rule, pattern in _SHAPES:
        for m in pattern.finditer(text):
            found.append(SecretMatch(rule, m.start(), m.end()))
    for kw in _KEYWORD.finditer(text):
        tail = _ASSIGNMENT_TAIL.match(text, kw.end())
        if tail and not _PLACEHOLDER_VALUE.match(tail.group("value")):
            found.append(SecretMatch("credential-assignment", tail.start("value"), tail.end("value")))
    for m in _CANDIDATE.finditer(text):
        if _looks_random(m.group(0)):
            found.append(SecretMatch("high-entropy-string", m.start(), m.end()))
    found.sort(key=lambda s: (s.start, -s.end))
    merged: list[SecretMatch] = []
    for item in found:
        if merged and item.start < merged[-1].end:
            if item.end > merged[-1].end:
                last = merged[-1]
                merged[-1] = SecretMatch(last.rule, last.start, item.end)
            continue
        merged.append(item)
    return merged


def contains_secret(text: str) -> bool:
    """True when `text` looks like it holds a secret. Text over the size cap cannot be checked in full, so it is
    treated as unsafe rather than assumed clean."""
    return len(text) > MAX_TEXT_CHARS or bool(find_secrets(text))


def redact_text(text: str) -> str:
    """`text` with every likely secret replaced by a marker. Text beyond the size cap is dropped, not scanned."""
    clipped = text[:MAX_TEXT_CHARS]
    out: list[str] = []
    cursor = 0
    for m in find_secrets(clipped):
        out.append(clipped[cursor : m.start])
        out.append(MARKER.format(rule=m.rule))
        cursor = m.end
    out.append(clipped[cursor:])
    result = "".join(out)
    return result + " [truncated]" if len(text) > MAX_TEXT_CHARS else result


def redact_value(value: Any, _depth: int = 0) -> Any:
    """Redacts every string inside nested dicts and lists (keys included). Deeper than MAX_DEPTH is refused."""
    if _depth > MAX_DEPTH:
        raise ValueError("The data is nested too deeply.")
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact_text(str(k)): redact_value(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v, _depth + 1) for v in value]
    return value


def reject_if_secret(value: Any, _depth: int = 0) -> None:
    """Raises SecretRejected when any string in `value` looks like a secret. Used on submissions from CI."""
    if _depth > MAX_DEPTH:
        raise ValueError("The data is nested too deeply.")
    if isinstance(value, str):
        if contains_secret(value):
            raise SecretRejected
    elif isinstance(value, dict):
        for k, v in value.items():
            reject_if_secret(str(k), _depth + 1)
            reject_if_secret(v, _depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            reject_if_secret(v, _depth + 1)


def length_class(length: int) -> str:
    """A coarse size for a secret, so the exact length (which helps guessing) is not kept."""
    if length < 8:
        return "under 8 characters"
    if length < 20:
        return "8 to 19 characters"
    if length < 40:
        return "20 to 39 characters"
    if length < 100:
        return "40 to 99 characters"
    return "100 characters or more"


def secret_fingerprint(key: bytes, value: str) -> str:
    """A keyed hash used only to tell whether the same secret appears again. It cannot be reversed without `key`.

    The caller must hold the secret value only long enough to call this and must never store or log it. `key` is a
    server secret that is not stored with the results, so database access alone does not allow guessing."""
    if len(key) < 16:
        raise ValueError("The fingerprint key is too short.")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
