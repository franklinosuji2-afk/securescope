"""The load-test script must never be pointable at the live site by accident."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "loadtest.py"
spec = importlib.util.spec_from_file_location("loadtest_script", SCRIPT)
assert spec is not None and spec.loader is not None
loadtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loadtest)


@pytest.mark.parametrize("base", ["http://127.0.0.1:8000", "http://localhost:8100", "http://[::1]:8000"])
def test_this_computer_is_allowed(base: str) -> None:
    loadtest.check_local(base)


@pytest.mark.parametrize(
    "base",
    [
        "https://getsecurescope.com",
        "https://securescope-api.onrender.com",
        "http://10.0.0.5:8000",
        "http://127.0.0.1.evil.example",
        "http://localhost.evil.example",
    ],
)
def test_other_addresses_are_refused(base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOADTEST_ALLOW_REMOTE", raising=False)
    with pytest.raises(SystemExit):
        loadtest.check_local(base)


def test_a_wrong_or_partial_override_does_not_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("yes", "1", "true", ""):
        monkeypatch.setenv("LOADTEST_ALLOW_REMOTE", value)
        with pytest.raises(SystemExit):
            loadtest.check_local("https://getsecurescope.com")


def test_only_the_exact_override_unlocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOADTEST_ALLOW_REMOTE", loadtest.ALLOW_REMOTE)
    loadtest.check_local("http://192.168.1.20:8000")


def test_percentiles() -> None:
    assert loadtest.percentile([], 95) == 0.0
    assert loadtest.percentile([5.0], 99) == 5.0
    values = [float(n) for n in range(1, 101)]
    assert loadtest.percentile(values, 50) in (50.0, 51.0)
    assert loadtest.percentile(values, 95) in (95.0, 96.0)
    assert loadtest.percentile(values, 100) == 100.0
