"""Scheduled scans: per-site schedules for people, and the cron endpoint for the scheduler."""

from __future__ import annotations

import asyncio
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import OrgContext, StateDep, client_key, request_id, require
from app.schemas.schedule import RunSummary, ScheduleList, ScheduleOut, ScheduleUpdate
from app.security.permissions import Permission
from app.security.target import TargetError, parse_target_url
from app.services.scheduler import run_due

router = APIRouter(prefix="/schedules", tags=["scheduled scans"])
internal_router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanManage = Annotated[OrgContext, Depends(require(Permission.TARGET_MANAGE))]
NOT_INCLUDED = "Scheduled scans are part of the Professional and Agency plans. Your plan does not include them."


@router.get("", response_model=ScheduleList)
async def list_schedules(state: StateDep, ctx: CanRead) -> ScheduleList:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    items = await asyncio.to_thread(state.schedules.list_for_organization, ctx.organization_id)
    return ScheduleList(available=plan.scheduled_scans, items=items)


@router.put("/{target_id}", response_model=ScheduleOut)
async def set_schedule(
    target_id: str, body: ScheduleUpdate, request: Request, state: StateDep, ctx: CanManage
) -> ScheduleOut:
    if not target_id.isalnum() or len(target_id) > 64:
        raise HTTPException(status_code=404, detail="Site not found.")
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    if not plan.scheduled_scans and body.frequency != "off":
        raise HTTPException(status_code=403, detail=NOT_INCLUDED)
    items = await asyncio.to_thread(state.schedules.list_for_organization, ctx.organization_id)
    site = next((i for i in items if i.target_id == target_id), None)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found, or it is not verified yet.")
    url = (body.url or f"https://{site.hostname}/").strip()
    try:
        _, host, _, _ = parse_target_url(url, state.settings)
    except TargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if host.lower() != site.hostname.lower():
        raise HTTPException(status_code=400, detail="The address must be on the verified site.")
    found = await asyncio.to_thread(
        state.schedules.set_schedule,
        ctx.organization_id,
        target_id,
        body.frequency,
        body.notify,
        url,
        ctx.principal.user.id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Site not found.")
    await asyncio.to_thread(
        state.audit.record,
        "schedule.updated",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="target",
        resource_id=target_id,
        request_id=request_id(request),
    )
    updated = await asyncio.to_thread(state.schedules.list_for_organization, ctx.organization_id)
    return next(i for i in updated if i.target_id == target_id)


@internal_router.post("/run-due", response_model=RunSummary)
async def run_due_schedules(
    request: Request,
    state: StateDep,
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> RunSummary:
    """Called by the Cloudflare cron. The endpoint does not exist unless a cron secret is configured."""
    secret = state.settings.cron_secret
    if secret is None:
        raise HTTPException(status_code=404, detail="Not found.")
    if not state.cron_limiter.check(client_key(request, state)):
        raise HTTPException(status_code=429, detail="Too many requests.")
    state.cron_limiter.record(client_key(request, state))
    given = (x_cron_secret or "").encode()
    if not hmac.compare_digest(given, secret.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="Not authorised.")
    return await run_due(state)
