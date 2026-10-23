from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import OrgContext, StateDep, client_key, download_organization_context, request_id, require
from app.billing.errors import PlanLimitError
from app.billing.plans import current_period
from app.core.logging import log_event
from app.reporting import reports
from app.reporting.compare import compare_scans
from app.reporting.csv_export import to_csv
from app.reporting.pdf import affected_url
from app.reporting.risk import overall_risk, severity_counts
from app.repositories.reports import ReportIntegrityError
from app.scanner.runner import execute_scan
from app.schemas.compare import ScanComparison
from app.schemas.scan import (
    ReportLink,
    ResultFinding,
    ScanCreate,
    ScanDetail,
    ScanList,
    ScanResults,
    ScanStatus,
)
from app.security.permissions import Permission
from app.security.target import TargetError, parse_target_url, validate_target

logger = logging.getLogger("securescope.api")
router = APIRouter(prefix="/scans", tags=["scans"])

REPORT_HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanCreate = Annotated[OrgContext, Depends(require(Permission.SCAN_CREATE))]
# Reports are downloaded through plain links, so the active organization may come as ?org= as well.
CanExport = Annotated[OrgContext, Depends(require(Permission.REPORT_EXPORT, download_organization_context))]


@dataclass(frozen=True)
class Actor:
    """Who starts a scan: a person with a session, or a CI token acting for the person who made it."""

    organization_id: str
    user_id: str


def actor_of(ctx: OrgContext) -> Actor:
    return Actor(ctx.organization_id, ctx.principal.user.id)


async def start_scan(state: StateDep, request: Request, ctx: Actor, url: str) -> ScanDetail:
    """Runs every safety check, then queues the scan. Used for new scans, retries and CI alike."""
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

    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    period_start, _ = current_period(datetime.now(UTC))
    try:
        scan_id = await asyncio.to_thread(
            state.repo.create_scan,
            ctx.organization_id,
            ctx.user_id,
            target.url,
            target.host,
            verified.id,
            plan.scans_per_month,
            period_start,
        )
    except PlanLimitError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await _audit_scan(state, request, ctx, "scan.created", scan_id)
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


async def _audit_scan(state: StateDep, request: Request, ctx: Actor, event: str, scan_id: str) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
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
    return await start_scan(state, request, actor_of(ctx), body.url)


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


@router.get("/{scan_id}/results", response_model=ScanResults)
async def get_results(scan_id: str, state: StateDep, ctx: CanRead) -> ScanResults:
    """The findings of one finished scan, with the overall risk rating and a severity summary."""
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(status_code=409, detail="The scan has not finished yet.")
    risk = overall_risk(detail)
    return ScanResults(
        scan_id=detail.id,
        host=detail.host,
        target_url=detail.target_url,
        status=detail.status,
        scanned_at=detail.created_at,
        error=detail.error,
        risk_level=risk.level,
        risk_label=risk.label,
        risk_summary=risk.summary,
        score=detail.score,
        grade=detail.grade,
        severity_counts=severity_counts(detail),
        findings=[
            ResultFinding(**f.model_dump(), affected_url=affected_url(detail, f)) for f in detail.findings
        ],
    )


@router.get("/{scan_id}/report/pdf", response_model=ReportLink)
async def report_pdf_link(scan_id: str, request: Request, state: StateDep, ctx: CanExport) -> ReportLink:
    """Makes the PDF report for a completed scan (once; it is kept) and returns a link that expires."""
    detail = await _load(state, ctx, scan_id)
    if detail.status is not ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="A report is available once a scan has finished successfully.",
        )
    user_id = ctx.principal.user.id
    if not state.report_limiter.check(user_id):
        raise HTTPException(status_code=429, detail="Too many report requests. Try again in a little while.")
    state.report_limiter.record(user_id)
    existing = await asyncio.to_thread(state.report_service.reports.get_meta, scan_id, ctx.organization_id)
    if existing is None:
        # Building a PDF is CPU work: one at a time, and off the event loop.
        async with state.report_semaphore:
            try:
                meta = await asyncio.to_thread(
                    state.report_service.ensure_report, detail, ctx.organization_id, user_id
                )
            except Exception:  # noqa: BLE001 - any rendering fault is reported the same way
                logger.exception("report generation failed", extra={"scan_id": scan_id})
                raise HTTPException(
                    status_code=500, detail="The report could not be created. Please try again."
                ) from None
        await _audit_scan(state, request, actor_of(ctx), "report.created", scan_id)
    else:
        meta = existing
    link = state.report_service.sign(meta.id, user_id, ctx.organization_id)
    url = (
        f"/api/v1/scans/{scan_id}/report/pdf/download"
        f"?org={ctx.organization_id}&expires={link.expires}&sig={link.signature}"
    )
    return ReportLink(
        report_id=meta.id,
        url=url,
        expires_at=datetime.fromtimestamp(link.expires, UTC),
        size_bytes=meta.size_bytes,
        created_at=meta.created_at,
    )


@router.get("/{scan_id}/report/pdf/download")
async def report_pdf_download(
    scan_id: str,
    request: Request,
    state: StateDep,
    ctx: CanExport,
    expires: Annotated[int, Query(ge=0)],
    sig: Annotated[str, Query(min_length=64, max_length=64, pattern="^[0-9a-f]+$")],
) -> Response:
    """Serves the stored PDF. Needs the signed-in session, an unexpired link issued to this same person for
    this organization, and ownership of the scan. Anything else looks like a missing report."""
    detail = await _load(state, ctx, scan_id)
    meta = await asyncio.to_thread(state.report_service.reports.get_meta, scan_id, ctx.organization_id)
    user_id = ctx.principal.user.id
    if meta is None or not state.report_service.is_valid(meta.id, user_id, ctx.organization_id, expires, sig):
        raise HTTPException(
            status_code=403, detail="This download link is invalid or has expired. Please request a new one."
        )
    try:
        loaded = await asyncio.to_thread(state.report_service.reports.get_file, meta.id, ctx.organization_id)
    except ReportIntegrityError:
        logger.error("stored report failed its checksum", extra={"report_id": meta.id})
        raise HTTPException(status_code=500, detail="This report could not be read.") from None
    if loaded is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    _, content = loaded
    await asyncio.to_thread(
        state.audit.record,
        "report.downloaded",
        organization_id=ctx.organization_id,
        actor_user_id=user_id,
        resource_type="scan",
        resource_id=scan_id,
        request_id=request_id(request),
    )
    filename = f"{meta.id}-{reports.safe_filename(detail, 'pdf')}"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    await _audit_scan(state, request, actor_of(ctx), "scan.cancelled", scan_id)
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
    await _audit_scan(state, request, actor_of(ctx), "scan.deleted", scan_id)


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
    created = await start_scan(state, request, actor_of(ctx), detail.target_url)
    await _audit_scan(state, request, actor_of(ctx), "scan.retried", scan_id)
    return created


@router.get("/{scan_id}/compare", response_model=ScanComparison)
async def compare(
    scan_id: str,
    state: StateDep,
    ctx: CanRead,
    other: Annotated[str, Query(min_length=1, max_length=64, alias="with")],
) -> ScanComparison:
    first = await _load(state, ctx, scan_id)
    second = await _load(state, ctx, other)
    if first.id == second.id:
        raise HTTPException(status_code=400, detail="Pick two different scans to compare.")
    if first.host != second.host:
        raise HTTPException(status_code=400, detail="Only scans of the same site can be compared.")
    for scan in (first, second):
        if scan.status != ScanStatus.COMPLETED:
            raise HTTPException(status_code=409, detail="Only completed scans can be compared.")
    return compare_scans(first, second)


@router.get("/{scan_id}/report")
async def export_report(
    scan_id: str,
    request: Request,
    state: StateDep,
    ctx: CanExport,
    format: Literal["json", "md", "html", "csv"] = "json",  # noqa: A002
) -> Response:
    detail = await _load(state, ctx, scan_id)
    if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
        raise HTTPException(status_code=409, detail="The scan has not finished yet.")
    media, extension, render = {
        "json": ("application/json", "json", reports.to_json),
        "md": ("text/markdown; charset=utf-8", "md", reports.to_markdown),
        "html": ("text/html; charset=utf-8", "html", reports.to_html),
        "csv": ("text/csv; charset=utf-8", "csv", to_csv),
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
    content = await asyncio.to_thread(render, detail)
    return Response(content=content, media_type=media, headers=headers)
