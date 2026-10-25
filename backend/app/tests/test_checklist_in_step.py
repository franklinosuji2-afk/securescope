"""The on-screen checklist (frontend) and the exported reports (backend) must group findings the same way."""

from __future__ import annotations

import re
from pathlib import Path

from app.scanner.checks import CHECK_LABELS, NOT_PASSED_AT_INFO

SOURCE = (Path(__file__).resolve().parents[3] / "frontend/src/components/Checklist.tsx").read_text()


def _frontend_checks() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    pattern = re.compile(r'^\s{2}(?:"([a-z0-9\-]+)"|([a-z0-9]+)): \{(.*?)^\s{2}\},', re.M | re.S)
    for m in pattern.finditer(SOURCE):
        block = re.search(r"prefixes: \[(.*?)\]", m.group(3), re.S)
        assert block is not None
        found[m.group(1) or m.group(2)] = set(re.findall(r'"([^"]+)"', block.group(1)))
    return found


def test_the_screen_checklist_has_the_same_checks_and_prefixes_as_the_reports() -> None:
    frontend = _frontend_checks()
    assert set(frontend) == set(CHECK_LABELS)
    for name, (_label, prefixes) in CHECK_LABELS.items():
        assert frontend[name] == set(prefixes), name


def test_the_screen_checklist_has_the_same_not_passed_at_info_list() -> None:
    block = re.search(r"const NOT_PASSED_AT_INFO = \[(.*?)\];", SOURCE, re.S)
    assert block is not None
    assert set(re.findall(r'"([^"]+)"', block.group(1))) == set(NOT_PASSED_AT_INFO)
