"""The scheduled-backup scripts keep the connection string out of output and refuse a role that can write.

They cannot be run here (they need Windows, Docker and the real database), so these tests read the text for the
properties that must never regress. The first real run is done by the owner (docs/OPERATIONS.md section 2).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCHEDULED = ROOT / "scripts" / "backup-scheduled.ps1"
SETUP = ROOT / "scripts" / "setup-backup-schedule.ps1"
CREATE_ROLE = ROOT / "scripts" / "create-backup-role.ps1"
pytestmark = pytest.mark.skipif(not SCHEDULED.exists(), reason="needs the repository's scripts folder")

SECRET_NAMES = (
    "$url",
    "$plain",
    "$secure",
    "$env:SECURESCOPE_BACKUP_URL",
    "$env:PGURL",
    "$owner",
    "$ownerUrl",
    "$ownerPassword",
    "$pw",
    "$sql",
)
OUTPUT_COMMANDS = (
    "Write-Host",
    "Write-Output",
    "Write-Log",
    "Add-Content",
    "Out-File",
    "Write-Error",
    "throw",
)


def code_lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.strip().startswith("#")]


@pytest.mark.parametrize("path", [SCHEDULED, SETUP, CREATE_ROLE])
def test_the_connection_string_is_never_printed_or_logged(path: Path) -> None:
    for line in code_lines(path):
        starts = [line.index(cmd) for cmd in OUTPUT_COMMANDS if cmd in line]
        if starts:
            printed = line[min(starts) :]  # what comes after the output command, not the test before it
            leaked = [name for name in SECRET_NAMES if name in printed]
            assert not leaked, f"{path.name}: {line.strip()}"


def test_setup_refuses_a_role_that_can_write_and_a_pooled_host() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "pg_write_all_data" in text and "rolsuper" in text and "has_table_privilege" in text
    assert "-pooler" in text
    # It stores the string encrypted for this Windows user, and the task keeps no password.
    assert "ConvertFrom-SecureString" in text
    register = next(ln for ln in text.splitlines() if "Register-ScheduledTask" in ln)
    assert "-Password" not in register and "-User" not in register


def test_the_job_never_keeps_fewer_than_three_and_always_clears_the_variable() -> None:
    text = SCHEDULED.read_text(encoding="utf-8")
    assert re.search(r"if \(\$Keep -lt 3\) \{ \$Keep = 3 \}", text)
    assert "Select-Object -Skip $Keep" in text
    assert (
        text.rstrip().endswith("}")
        and "Remove-Item Env:SECURESCOPE_BACKUP_URL" in text.split("finally", 1)[-1]
    )
    # Old dumps are removed only after a new, non-empty one exists.
    assert text.index("No new backup file was written") < text.index("Remove-Item $file.FullName")


def test_the_role_script_hides_both_passwords_and_grants_only_reading() -> None:
    text = CREATE_ROLE.read_text(encoding="utf-8")
    assert '.Replace($pw, "<hidden>").Replace($ownerPassword, "<hidden>")' in text
    assert text.index('.Replace($pw, "<hidden>")') < text.index("Write-Host $text")
    assert "Set-Clipboard" in text
    grants = [ln for ln in text.splitlines() if re.match(r"\s*(GRANT|ALTER DEFAULT PRIVILEGES)", ln)]
    assert grants and not any(
        w in ln.upper() for ln in grants for w in ("INSERT", "UPDATE", "DELETE", "ALL PRIVILEGES")
    )
    assert "SUPERUSER" not in text.upper().replace("SUPERUSER: ", "").replace("ROLSUPER", "")
