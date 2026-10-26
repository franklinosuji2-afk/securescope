"""POST /app/scans (browser upload): the processing slot, cancellation, hard timeout, shutdown and consistency.

The slot of the worker thread is only freed when that thread has really finished, a cancelled or timed-out request
never leaves findings or a completed run behind, and neither is counted. These tests drive a second application
instance on the same database with its own event loop, so a request can be cancelled the way a server cancels it."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.v1.app_scans as module
import app.appscan.pipeline as pipeline
from app.models.app_scan import AppFindingRow, AppScanRow
from app.tests.conftest import signup
from app.tests.test_appscan_ci_tokens import rows, run_on_a_second_instance
from app.tests.test_appscan_routes import ADV, API, LOCK, Fake, make_app, project, runs_used, scan


@pytest.fixture
def env(make_settings, mailer):  # type: ignore[no-untyped-def]
    with make_app(make_settings, mailer) as client:
        signup(client, "owner@example.com", "Org")
        client.app.state.s.app_source = Fake({"lodash": [ADV]})  # type: ignore[attr-defined]
        yield client, project(client)


def headers_of(client: TestClient) -> dict[str, str]:
    cookies = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    return {"Cookie": cookies, "X-CSRF-Token": client.headers["X-CSRF-Token"]}


def body_of(pid: str) -> bytes:
    return json.dumps(
        {
            "project_id": pid,
            "kinds": ["dependency"],
            "files": [{"name": "package-lock.json", "content": LOCK}],
        }
    ).encode()


def block_the_scan(monkeypatch: pytest.MonkeyPatch) -> tuple[threading.Event, threading.Event, list[int]]:
    """Makes the scanning step wait in its worker thread until released. Returns (started, release, calls)."""
    started, release = threading.Event(), threading.Event()
    calls: list[int] = []
    real = pipeline.run_dependency_scan

    def slow(*args: Any, **kw: Any) -> Any:
        calls.append(1)
        started.set()
        release.wait(10)
        return real(*args, **kw)

    monkeypatch.setattr(module, "run_dependency_scan", slow)
    return started, release, calls


def statuses(client: TestClient) -> list[str]:
    return [str(s.status) for s in rows(client, AppScanRow)]


async def post(http: Any, client: TestClient, pid: str) -> Any:
    return await http.post(
        f"{API}/scans",
        content=body_of(pid),
        headers={**headers_of(client), "Content-Type": "application/json"},
    )


def test_a_cancelled_upload_keeps_the_slot_until_its_thread_ends(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    client, pid = env
    started, release, _calls = block_the_scan(monkeypatch)

    async def scenario(app: Any, http: Any) -> tuple[bool, bool, str]:
        state = app.state.s
        state.app_source = Fake({"lodash": [ADV]})
        request = asyncio.ensure_future(post(http, client, pid))
        await asyncio.to_thread(started.wait, 5)
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        held = state.app_scan_semaphore.locked()
        # while the thread still runs the run is already over, honestly, and nothing is stored from it
        ended = ""
        for _ in range(100):
            ended = (await asyncio.to_thread(statuses, client))[0]
            if ended == "interrupted":
                break
            await asyncio.sleep(0.05)
        release.set()
        await asyncio.sleep(0.4)
        return held, state.app_scan_semaphore.locked(), ended

    held, held_after, ended = run_on_a_second_instance(make_settings, mailer, scenario)
    assert held is True and held_after is False and ended == "interrupted"
    assert statuses(client) == ["interrupted"]
    assert rows(client, AppFindingRow) == [] and runs_used(client) == 0


def test_a_second_upload_cannot_start_work_while_a_cancelled_scans_thread_still_runs(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    client, pid = env
    started, release, calls = block_the_scan(monkeypatch)

    async def scenario(app: Any, http: Any) -> int:
        app.state.s.app_source = Fake({"lodash": [ADV]})
        first = asyncio.ensure_future(post(http, client, pid))
        await asyncio.to_thread(started.wait, 5)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        second = asyncio.ensure_future(post(http, client, pid))
        await asyncio.sleep(0.5)
        running_threads = len(calls)  # the second must still be waiting for the slot
        release.set()
        response = await second
        assert response.status_code == 201, response.text
        return running_threads

    assert run_on_a_second_instance(make_settings, mailer, scenario) == 1
    assert sorted(statuses(client)) == ["completed", "interrupted"]
    assert runs_used(client) == 1  # only the completed run counts


def test_a_scan_that_completes_stores_its_result_once_and_frees_the_slot(env, make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    client, pid = env

    async def scenario(app: Any, http: Any) -> tuple[int, bool]:
        app.state.s.app_source = Fake({"lodash": [ADV]})
        response = await post(http, client, pid)
        return response.status_code, app.state.s.app_scan_semaphore.locked()

    code, locked = run_on_a_second_instance(make_settings, mailer, scenario)
    assert code == 201 and locked is False
    assert statuses(client) == ["completed"]
    assert len(rows(client, AppFindingRow)) == 1 and runs_used(client) == 1


def test_a_scan_over_the_hard_limit_ends_failed_uncounted_and_keeps_the_slot_until_the_thread_ends(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    client, pid = env
    started, release, _calls = block_the_scan(monkeypatch)
    monkeypatch.setattr(module, "SCAN_HARD_SECONDS", 0.3)

    async def scenario(app: Any, http: Any) -> tuple[Any, bool, bool]:
        state = app.state.s
        state.app_source = Fake({"lodash": [ADV]})
        response = await post(http, client, pid)
        held = state.app_scan_semaphore.locked()
        release.set()
        await asyncio.sleep(0.4)
        return response, held, state.app_scan_semaphore.locked()

    response, held, held_after = run_on_a_second_instance(make_settings, mailer, scenario)
    assert response.status_code == 201 and response.json()["status"] == "failed"
    assert held is True and held_after is False
    assert statuses(client) == ["failed"]
    assert rows(client, AppFindingRow) == [] and runs_used(client) == 0  # nothing from the late thread


def test_cancelling_while_waiting_for_a_slot_takes_no_slot_and_starts_no_work(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    client, pid = env
    started, release, calls = block_the_scan(monkeypatch)

    async def scenario(app: Any, http: Any) -> int:
        app.state.s.app_source = Fake({"lodash": [ADV]})
        first = asyncio.ensure_future(post(http, client, pid))
        await asyncio.to_thread(started.wait, 5)
        second = asyncio.ensure_future(post(http, client, pid))
        await asyncio.sleep(0.5)  # the second is waiting for the slot
        second.cancel()
        await asyncio.gather(second, return_exceptions=True)
        release.set()
        assert (await first).status_code == 201
        await asyncio.sleep(0.3)
        assert not app.state.s.app_scan_semaphore.locked()
        return len(calls)

    assert run_on_a_second_instance(make_settings, mailer, scenario) == 1  # the waiting scan never ran
    assert sorted(statuses(client)) == ["completed", "interrupted"]
    assert len(rows(client, AppFindingRow)) == 1 and runs_used(client) == 1


def test_shutdown_with_a_browser_scan_in_flight_leaves_a_consistent_database(  # type: ignore[no-untyped-def]
    env, make_settings, mailer, monkeypatch
) -> None:
    client, pid = env
    started, release, _calls = block_the_scan(monkeypatch)

    async def scenario(app: Any, http: Any) -> None:
        app.state.s.app_source = Fake({"lodash": [ADV]})
        request = asyncio.ensure_future(post(http, client, pid))
        await asyncio.to_thread(started.wait, 5)
        request.cancel()  # what a server does to requests still running at shutdown
        await asyncio.gather(request, return_exceptions=True)
        threading.Timer(1.0, release.set).start()  # the thread ends after the lifespan has ended

    begun = time.perf_counter()
    run_on_a_second_instance(make_settings, mailer, scenario)
    assert time.perf_counter() - begun < 8
    assert statuses(client) == ["interrupted"]
    assert rows(client, AppFindingRow) == [] and runs_used(client) == 0


def test_the_upload_limits_still_apply(env) -> None:  # type: ignore[no-untyped-def]
    client, pid = env
    huge = {
        "project_id": pid,
        "kinds": ["dependency"],
        "files": [{"name": "requirements.txt", "content": "a" * (7 * 1024 * 1024)}],
    }
    assert client.post(f"{API}/scans", json=huge).status_code == 413
    six = {f"dir{i}/package-lock.json": LOCK for i in range(6)}
    assert scan(client, pid, six).status_code == 422
    assert statuses(client) == [] and runs_used(client) == 0
    assert scan(client, pid).status_code == 201
