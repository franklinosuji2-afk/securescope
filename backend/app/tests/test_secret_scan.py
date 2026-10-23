"""The secret scanner finds real-looking secrets and ignores placeholders; the repository itself is clean."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "scan_secrets.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="needs the repository's scripts folder")


def load() -> Any:
    spec = importlib.util.spec_from_file_location("scan_secrets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Built from pieces so this file does not itself look like a leaked secret.
LOOKS_REAL = {
    "GitHub token": "gh" + "p_" + "a1" * 18,
    "AWS access key id": "AK" + "IA" + "B" * 16,
    "Private key block": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "SecureScope API token": "ss" + "k_" + "Ab3" * 15,
    "SecureScope webhook secret": "whs" + "ec_" + "f0" * 24,
    "Database URL with password": "postgresql+psycopg://app:" + "s3cretPw99" + "@ep-x.neon.tech/db",
}
PLACEHOLDERS = [
    "postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require",
    "postgresql+psycopg://postgres:postgres@db:5432/securescope",
    "SECURESCOPE_WEBHOOK_SIGNING_KEY=<32 or more random characters>",
    "Authorization: Bearer <token>",
]


@pytest.mark.parametrize(("kind", "text"), LOOKS_REAL.items())
def test_real_looking_secrets_are_found(kind: str, text: str) -> None:
    found: list[str] = []
    load().scan_text("x", f"value = {text}", found)
    assert found and kind in found[0]


@pytest.mark.parametrize("text", PLACEHOLDERS)
def test_placeholders_are_not_flagged(text: str) -> None:
    found: list[str] = []
    load().scan_text("x", text, found)
    assert found == []


@pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout"
)
def test_the_tracked_files_hold_no_secrets() -> None:
    result = subprocess.run(
        ["python", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode == 0, result.stdout
