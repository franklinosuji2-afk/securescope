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
from app.security.target import TargetError, parse_target_url, validate_target

logger = logging.getLogger("securescope.api")
router = APIRouter(prefix="/scans", tags=["scans"])

REPORT_HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanCreate = Annotated[OrgContext, Depends(require(Permission.SCAN_CREATE))]
CanExport = Annotated[OrgContext, Depends(require(Permission.REPORT_EXPORT))]


async def _start_scan(state: StateDep, request: Request, ctx: OrgContext, url: str) -> ScanDetail:
    """Runs every safety check, then queues the scan. Used for new scans and for retries alike."""
    try:
        _, host, _, _ = parse_target_url(url, state.settings)
    except TargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Ownership is checked before any DNS lookup or outbound request is made for this host.
    verified = await asyncio.to_thread(state.targets.find_verified, ctx.organization_id, host)
    if verified is None:
        known = await asyncio.to_thread(state.targets.find_by_host, ctx.organization_id, host)
        if known is not None and known.status == "reverify":
            raise HTTPException(
                status_code=403,
                detail=(
                    f"The ownership proof for {host} has expired. "
                    "Open Targets, press New challenge, publish it and verify again."
                ),
            )
        raise HTTPException(
            status_code=403,
            detail=f"Ownership of {host} has not been verified. Add and verify it under Targets first.",
        )
    try:
        target = await validate_target(url, state.settings)
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
        state.repo.create_scan,
        ctx.organization_id,
        ctx.principal.user.id,
        target.url,
        target.host,
        verified.id,
    )
    await _audit(state, request, ctx, "scan.created", scan_id)
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
    log_event(logger, "scan queued", scan_id=scan_id, host=target.host, organization_id=ctx.organization_id)
    detail = await asyncio.to_thread(state.repo.get_scan, scan_id, ctx.organization_id)
    if detail is None:  # created a moment ago in this organization; only possible on a storage fault
        raise HTTPException(status_code=500, detail="The scan could not be loaded.")
    return detail


async def _audit(state: StateDep, request: Request, ctx: OrgContext, event: str, scan_id: str) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="scan",
        resource_id=scan_id,
        request_id=request_id(request),
    )


@router.post("", response_model=ScanDetail, status_code=202)
async def create_scan(body: ScanCreate, request: Request, state: StateDep, ctx: CanCreate) -> ScanDetail:
    if not body.authorization_confirmed:
        raise HTTPException(
            status_code=400,
            detail="You must confirm that you own this target or have written authorization to test it.",
        )
    return await _start_scan(state, request, ctx, body.url)


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


@router.post("/{scan_id}/cancel", response_model=ScanDetail)
async def cancel_scan(scan_id: str, request: Request, state: StateDep, ctx: CanCreate) -> ScanDetail:
    detail = await _load(state, ctx, scan_id)
    if detail.status not in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(
            status_code=409, detail="This scan has already finished, so it cannot be cancelled."
        )
    # The database decides who wins a race with the scanner finishing at the same moment.
    if not await asyncio.to_thread(state.repo.cancel_scan, scan_id, ctx.organization_id):
        raise HTTPException(
            status_code=409, detail="This scan has already finished, so it cannot be cancelled."
        )
    task = state.scan_tasks.get(scan_id)
    if task is not None:
        task.cancel()
    await _audit(state, request, ctx, "scan.cancelled", scan_id)
    return await _load(state, ctx, scan_id)


@router.delete("/{scan_id}", status_code=204)
async def delete_scan(scan_id: str, request: Request, state: StateDep, ctx: CanCreate) -> None:
    """Permanently removes a finished scan and its findings from this organization."""
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(
            status_code=409, detail="This scan is still running. Cancel it first, then delete it."
        )
    if not await asyncio.to_thread(state.repo.delete_scan, scan_id, ctx.organization_id):
        raise HTTPException(
            status_code=409, detail="This scan could not be deleted because it is still running."
        )
    await _audit(state, request, ctx, "scan.deleted", scan_id)


@router.post("/{scan_id}/retry", response_model=ScanDetail, status_code=202)
async def retry_scan(scan_id: str, request: Request, state: StateDep, ctx: CanCreate) -> ScanDetail:
    """Starts a new scan of the same address as a finished one ("scan again" / "retry").

    Ownership, target rules and rate limits apply again, exactly as for a new scan.
    """
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(
            status_code=409, detail="This scan is still running, so it cannot be run again yet."
        )
    created = await _start_scan(state, request, ctx, detail.target_url)
    await _audit(state, request, ctx, "scan.retried", scan_id)
    return created


@router.get("/{scan_id}/report")
async def export_report(
    scan_id: str,
    request: Request,
    state: StateDep,
    ctx: CanExport,
    format: Literal["json", "md", "html", "pdf"] = "json",  # noqa: A002
) -> Response:
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(status_code=409, detail="The scan has not finished yet.")
    media, extension, render = {
        "json": ("application/json", "json", reports.to_json),
        "md": ("text/markdown; charset=utf-8", "md", reports.to_markdown),
        "html": ("text/html; charset=utf-8", "html", reports.to_html),
        "pdf": ("application/pdf", "pdf", reports.to_pdf),
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
    # Building a PDF is CPU work, so it runs off the event loop.
    content = await asyncio.to_thread(render, detail)
    return Response(content=content, media_type=media, headers=headers)
