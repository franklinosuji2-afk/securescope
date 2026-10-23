"""Fails when something that looks like a real secret is in the repository or in its history.

    python scripts/scan_secrets.py            # files tracked by git, as they are now
    python scripts/scan_secrets.py --history  # every line ever added on any branch

Only the standard library and git are needed, so it runs the same on a laptop and in CI. It prints the file, the
line and the kind of secret, never the value. It is a safety net for common token shapes, not a replacement for
keeping secrets out of the code in the first place.
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"
    ),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Google client secret": re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{10,}\b"),
    "Brevo or Resend key": re.compile(r"\bxkeysib-[A-Za-z0-9-]{20,}\b|\bre_[A-Za-z0-9]{24,}\b"),
    "Provider secret key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "SecureScope API token": re.compile(r"\bssk_[A-Za-z0-9_-]{40,}\b"),
    "SecureScope webhook secret": re.compile(r"\bwhsec_[A-Za-z0-9]{40,}\b"),
    "Database URL with password": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?://[^:\s\"'/@]+:(?!(?i:password|secret|postgres|change)|\*+|<)[^@\s\"'<]{6,}@"
        r"(?!localhost|127\.0\.0\.1|db\b|postgres\b|HOST\b)[A-Za-z0-9.-]+"
    ),
}
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env|.*\.pem|.*\.key|client_secret.*\.json|.*\.dump|.*\.sqlite3?)$")
ALLOWED_FILES = {".env.example"}


def git(*args: str) -> str:
    # Fixed program and arguments written in this file; nothing from the repository is passed to a shell.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    return result.stdout


def scan_text(label: str, text: str, found: list[str]) -> None:
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                found.append(f"{label}:{number}: {kind}")


def main() -> int:
    history = "--history" in sys.argv
    found: list[str] = []
    for name in git("ls-files").splitlines():
        if name not in ALLOWED_FILES and FORBIDDEN_FILES.search(name):
            found.append(f"{name}: a file type that should never be committed")
            continue
        try:
            with open(name, encoding="utf-8", errors="replace") as handle:
                scan_text(name, handle.read(), found)
        except OSError:
            continue
    if history:
        log = git("log", "--all", "-p", "--no-color", "-U0", "--format=commit %h")
        commit = "?"
        for line in log.splitlines():
            if line.startswith("commit "):
                commit = line.split()[1]
            elif line.startswith("+") and not line.startswith("+++"):
                for kind, pattern in PATTERNS.items():
                    if pattern.search(line):
                        found.append(f"history commit {commit}: {kind}")
    for item in sorted(set(found)):
        print(item)
    if found:
        print(
            f"{len(set(found))} possible secret(s). Remove them, rotate the credential, and rewrite history if needed."
        )
        return 1
    print("No secrets found" + (" in files or history." if history else " in tracked files."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
