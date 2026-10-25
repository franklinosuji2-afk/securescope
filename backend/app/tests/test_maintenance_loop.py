"""The hourly clean-up keeps running when one of its steps fails.

Retention promises (history windows, audit log, analytics) are kept by this loop. If one failed database call
ended it, nothing would be cleaned up again until the next restart, and a service that is kept warm can run for
weeks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app import main


class Recorder:
    """Stands in for a repository: counts calls, and can be told to fail the first few."""

    def __init__(self, fail_first: int = 0) -> None:
        self.calls = 0
        self._fail_first = fail_first

    def __call__(self, *args: Any) -> int:
        self.calls += 1
        if self.calls <= self._fail_first:
            raise RuntimeError("the database is still waking up")
        return 0


def fake_state(history: Recorder, audit: Recorder, sessions: Recorder) -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(admin_email="", analytics_retention_days=90, audit_retention_days=365),
        plans=SimpleNamespace(assign_internal_to_operator=Recorder()),
        repo=SimpleNamespace(delete_expired_history=history),
        accounts=SimpleNamespace(
            purge_expired_sessions=sessions,
            purge_expired_oauth_states=Recorder(),
            purge_old_invitations=Recorder(),
        ),
        analytics=SimpleNamespace(delete_older_than=Recorder()),
        audit=SimpleNamespace(delete_older_than=audit),
    )


def run_for(state: Any, seconds: float) -> None:
    async def go() -> None:
        try:
            await asyncio.wait_for(main._maintenance_loop(state), timeout=seconds)
        except TimeoutError:
            pass  # the loop never ends by itself

    asyncio.run(go())


def test_a_failing_step_does_not_stop_the_steps_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAINTENANCE_INTERVAL_SECONDS", 3600)
    history = Recorder(fail_first=1_000)  # always fails
    audit, sessions = Recorder(), Recorder()
    run_for(fake_state(history, audit, sessions), 1)
    assert history.calls == 1
    assert sessions.calls == 1 and audit.calls == 1  # the later steps still ran


def test_the_loop_runs_again_after_a_failed_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "MAINTENANCE_INTERVAL_SECONDS", 0.05)
    history = Recorder(fail_first=1)  # the first pass fails, later passes work
    audit, sessions = Recorder(), Recorder()
    run_for(fake_state(history, audit, sessions), 1)
    assert history.calls >= 3
    assert audit.calls >= 3
