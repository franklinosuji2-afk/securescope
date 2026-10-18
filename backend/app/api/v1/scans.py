from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import OrgContext, StateDep, client_key, request_id, require
from app.core.logging import log_event
from app.reporting import reports
from app.scanner.runner import execute_scan
from app.schemas.scan import ScanCreate, ScanDetail, ScanList, ScanStatus
from app.security.permissions import Permission
from app.security.target import TargetError, validate_target

logger = logging.getLogger("securescope.api")
router = APIRouter(prefix="/scans", tags=["scans"])

REPORT_HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanCreate = Annotated[OrgContext, Depends(require(Permission.SCAN_CREATE))]
CanExport = Annotated[OrgContext, Depends(require(Permission.REPORT_EXPORT))]


@router.post("", response_model=ScanDetail, status_code=202)
async def create_scan(body: ScanCreate, request: Request, state: StateDep, ctx: CanCreate) -> ScanDetail:
    if not body.authorization_confirmed:
        raise HTTPException(
            status_code=400,
            detail="You must confirm that you own this target or have written authorization to test it.",
        )
    try:
        target = await validate_target(body.url, state.settings)
    except TargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client = f"{ctx.organization_id}:{client_key(request, state)}"
    if not state.client_limiter.check(client):
        raise HTTPException(status_code=429, detail="Too many scans from your account. Try again later.")
    target_key = f"{ctx.organization_id}:{target.host}"
    if not state.target_limiter.check(target_key):
        raise HTTPException(
            status_code=429, detail="This target was scanned too often recently. Try again later."
        )
    if state.pending >= state.settings.max_concurrent_scans * 4:
        raise HTTPException(status_code=429, detail="The scanner is busy. Try again in a minute.")
    state.client_limiter.record(client)
    state.target_limiter.record(target_key)

    scan_id = await asyncio.to_thread(
        state.repo.create_scan, ctx.organization_id, ctx.principal.user.id, target.url, target.host
    )
    await asyncio.to_thread(
        state.audit.record,
        "scan.created",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="scan",
        resource_id=scan_id,
        request_id=request_id(request),
    )
    task = asyncio.create_task(
        execute_scan(scan_id, target.url, target.host, state.settings, state.repo, state.semaphore)
    )
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    log_event(logger, "scan queued", scan_id=scan_id, host=target.host, organization_id=ctx.organization_id)
    detail = await asyncio.to_thread(state.repo.get_scan, scan_id, ctx.organization_id)
    assert detail is not None
    return detail


@router.get("", response_model=ScanList)
async def list_scans(
    state: StateDep,
    ctx: CanRead,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScanList:
    items, total = await asyncio.to_thread(state.repo.list_scans, ctx.organization_id, limit, offset)
    return ScanList(items=items, total=total)


async def _load(state: StateDep, ctx: OrgContext, scan_id: str) -> ScanDetail:
    if not scan_id.isalnum() or len(scan_id) > 64:
        raise HTTPException(status_code=404, detail="Scan not found.")
    detail = await asyncio.to_thread(state.repo.get_scan, scan_id, ctx.organization_id)
    if detail is None:  # also returned for scans of other organizations
        raise HTTPException(status_code=404, detail="Scan not found.")
    return detail


@router.get("/{scan_id}", response_model=ScanDetail)
async def get_scan(scan_id: str, state: StateDep, ctx: CanRead) -> ScanDetail:
    return await _load(state, ctx, scan_id)


@router.get("/{scan_id}/report")
async def export_report(
    scan_id: str,
    request: Request,
    state: StateDep,
    ctx: CanExport,
    format: Literal["json", "md", "html"] = "json",  # noqa: A002
) -> Response:
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(status_code=409, detail="The scan has not finished yet.")
    media, extension, content = {
        "json": ("application/json", "json", reports.to_json),
        "md": ("text/markdown; charset=utf-8", "md", reports.to_markdown),
        "html": ("text/html; charset=utf-8", "html", reports.to_html),
    }[format]
    headers = {"Content-Disposition": f'attachment; filename="{reports.safe_filename(detail, extension)}"'}
    if format == "html":
        headers["Content-Security-Policy"] = REPORT_HTML_CSP
    await asyncio.to_thread(
        state.audit.record,
        "report.exported",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="scan",
        resource_id=scan_id,
        request_id=request_id(request),
    )
    return Response(content=content(detail), media_type=media, headers=headers)
