"""A fake secret that the redaction rules recognise, and a check that it appears nowhere it should not.

The value is assembled at run time so this file never contains a string that looks like a real credential (the
repository's own secret scan would rightly flag it). Later App Scanning steps use `assert_no_canary` on database
rows, API bodies, PDF text, webhook payloads, alert emails and captured logs.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def make_canary() -> str:
    """A new random GitHub-token-shaped value. Different on every call so a stale copy cannot hide a leak."""
    return "gh" + "p_" + "".join(secrets.choice(_ALPHABET + _ALPHABET.lower()) for _ in range(36))


def assert_no_canary(canary: str, *haystacks: object) -> None:
    """Fails if the canary, or any 8-character piece of it, appears in any haystack (text, bytes, or repr)."""
    pieces = {canary} | {canary[i : i + 8] for i in range(0, len(canary) - 7)}
    for haystack in haystacks:
        text = haystack.decode("utf-8", "replace") if isinstance(haystack, bytes) else str(haystack)
        for piece in pieces:
            assert piece not in text, "a secret (or part of one) was found in output that must not contain it"


def capture_logs() -> tuple[logging.Handler, list[str]]:
    """A handler that collects every formatted log line, for `assert_no_canary`. The caller adds and removes it."""
    lines: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    return _Collect(), lines


def all_text(parts: Iterable[object]) -> str:
    return "\n".join(str(p) for p in parts)
