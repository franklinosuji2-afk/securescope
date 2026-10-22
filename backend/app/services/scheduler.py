"""Runs the scans that are due. Called by the cron endpoint, never by a browser.

Each due schedule goes through the same safety checks as a scan someone starts by hand: the site must still
be verified, the address is validated again, and the scan counts against the workspace's monthly allowance.
Nothing here can scan a site that is not verified for the workspace that owns the schedule.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.billing.errors import PlanLimitError
from app.billing.plans import current_period
from app.core.logging import log_event
from app.scanner.runner import execute_scan
from app.schemas.schedule import RunSummary
from app.security.target import TargetError, parse_target_url, validate_target

if TYPE_CHECKING:
    from app.api.deps import AppState
    from app.repositories.schedules import DueSchedule

logger = logging.getLogger("securescope.scheduler")
MAX_JOBS_PER_RUN = 3


async def _run_one(state: AppState, item: DueSchedule) -> tuple[bool, int]:
    """Returns (scan started, alerts sent)."""
    plan = await state.entitlements.plan_for_async(item.organization_id)
    if not plan.scheduled_scans:
        await asyncio.to_thread(state.schedules.disable, item.id)
        return False, 0
    verified = await asyncio.to_thread(state.targets.find_verified, item.organization_id, item.hostname)
    if verified is None:
        await asyncio.to_thread(state.schedules.record_outcome, item.id, "skipped: site is no longer verified")
        return False, 0
    try:
        _, host, _, _ = parse_target_url(item.url, state.settings)
        if host.lower() != item.hostname.lower():
            raise TargetError("The scheduled address is not on the verified site.")
        target = await validate_target(item.url, state.settings)
    except TargetError as exc:
        await asyncio.to_thread(state.schedules.record_outcome, item.id, f"skipped: {exc}")
        return False, 0
    period_start, _ = current_period(datetime.now(UTC))
    try:
        scan_id = await asyncio.to_thread(
            state.repo.create_scan,
            item.organization_id,
            item.created_by,
            target.url,
            target.host,
            verified.id,
            plan.scans_per_month,
            period_start,
        )
    except PlanLimitError:
        await asyncio.to_thread(
            state.schedules.record_outcome, item.id, "skipped: the monthly scan allowance is used up"
        )
        return False, 0
    await asyncio.to_thread(
        state.audit.record,
        "scan.scheduled",
        organization_id=item.organization_id,
        resource_type="scan",
        resource_id=scan_id,
    )
    task = asyncio.create_task(
        execute_scan(scan_id, target.url, target.host, state.settings, state.repo, state.semaphore)
    )
    state.tasks.add(task)
    state.scan_tasks[scan_id] = task

    def _forget(done: asyncio.Task[None]) -> None:
        state.tasks.discard(done)
        if state.scan_tasks.get(scan_id) is done:
            del state.scan_tasks[scan_id]

    task.add_done_callback(_forget)
    await asyncio.wait({task})  # does not raise if the scan was cancelled meanwhile
    current = await asyncio.to_thread(state.repo.get_scan, scan_id, item.organization_id)
    if current is None:
        return True, 0
    outcome = f"{current.status.value}, score {current.score}" if current.score is not None else current.status.value
    await asyncio.to_thread(state.schedules.record_outcome, item.id, outcome, scan_id)
    sent = 0
    if item.notify:
        previous_id = await asyncio.to_thread(
            state.schedules.previous_completed_scan_id, item.organization_id, current.host, scan_id
        )
        previous = (
            await asyncio.to_thread(state.repo.get_scan, previous_id, item.organization_id)
            if previous_id
            else None
        )
        sent = await state.alerts.notify_async(item.organization_id, previous, current)
    log_event(logger, "scheduled scan finished", scan_id=scan_id, host=item.hostname, alerts=sent)
    return True, sent


async def run_due(state: AppState, max_jobs: int = MAX_JOBS_PER_RUN) -> RunSummary:
    due = await asyncio.to_thread(state.schedules.claim_due, datetime.now(UTC), max_jobs)
    started = alerts = skipped = 0
    for item in due:
        try:
            ran, sent = await _run_one(state, item)
        except Exception:  # one broken schedule must not stop the others  # noqa: BLE001
            logger.exception("scheduled run failed", extra={"fields": {"schedule_id": item.id}})
            await asyncio.to_thread(state.schedules.record_outcome, item.id, "error: the run failed")
            skipped += 1
            continue
        started += int(ran)
        alerts += sent
        skipped += int(not ran)
    return RunSummary(due=len(due), scans_started=started, alerts_sent=alerts, skipped=skipped)
