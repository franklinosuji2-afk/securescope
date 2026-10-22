"""Agency workspace: clients, the agency dashboard, report branding and shared report links.

Everything here is limited to the signed-in workspace and to plans that include client workspaces. The
public part (``/shared``) serves one report for one unguessable, expiring, revocable link and nothing else.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import OrgContext, StateDep, client_key, request_id, require
from app.models.target import TargetRow
from app.reporting.risk import counting_findings
from app.repositories.agency import DuplicateClientError
from app.repositories.reports import ReportIntegrityError
from app.schemas.agency import (
    AssignClient,
    Branding,
    ClientCreate,
    ClientList,
    ClientOut,
    ClientUpdate,
    Dashboard,
    DashboardClient,
    DashboardSite,
    SeverityCounts,
    ShareCreate,
    ShareCreated,
    SharedReportInfo,
    ShareList,
)
from app.schemas.scan import SEVERITY_ORDER, FindingStatus, ScanDetail, ScanStatus
from app.security.permissions import Permission

logger = logging.getLogger("securescope.agency")

router = APIRouter(prefix="/agency", tags=["agency"])
public_router = APIRouter(prefix="/shared", tags=["shared reports"])

CanRead = Annotated[OrgContext, Depends(require(Permission.CLIENT_READ))]
CanManage = Annotated[OrgContext, Depends(require(Permission.CLIENT_MANAGE))]
CanShare = Annotated[OrgContext, Depends(require(Permission.REPORT_SHARE))]

GRADE_ORDER = "ABCDF"
NOT_FOUND = "Not found."


async def _gate(state: StateDep, ctx: OrgContext) -> None:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    if not plan.client_workspace:
        raise HTTPException(
            status_code=403,
            detail="Client workspaces are part of the Agency plan. Your plan does not include them.",
        )


def _valid_id(value: str) -> None:
    if not value.isalnum() or len(value) > 64:
        raise HTTPException(status_code=404, detail=NOT_FOUND)


async def _audit(
    state: StateDep, request: Request, ctx: OrgContext, event: str, resource_type: str, resource_id: str
) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id(request),
    )


# --- clients ----------------------------------------------------------------------------------------


@router.get("/clients", response_model=ClientList)
async def list_clients(state: StateDep, ctx: CanRead) -> ClientList:
    await _gate(state, ctx)
    return ClientList(items=await asyncio.to_thread(state.agency.list_clients, ctx.organization_id))


@router.post("/clients", response_model=ClientOut, status_code=201)
async def create_client(body: ClientCreate, request: Request, state: StateDep, ctx: CanManage) -> ClientOut:
    await _gate(state, ctx)
    try:
        client = await asyncio.to_thread(
            state.agency.create_client, ctx.organization_id, body.name, body.contact_email, body.notes
        )
    except DuplicateClientError as exc:
        raise HTTPException(status_code=409, detail="You already have a client with this name.") from exc
    await _audit(state, request, ctx, "client.created", "client", client.id)
    return client


@router.get("/clients/{client_id}", response_model=ClientOut)
async def get_client(client_id: str, state: StateDep, ctx: CanRead) -> ClientOut:
    await _gate(state, ctx)
    _valid_id(client_id)
    client = await asyncio.to_thread(state.agency.get_client, client_id, ctx.organization_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client


@router.put("/clients/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: str, body: ClientUpdate, request: Request, state: StateDep, ctx: CanManage
) -> ClientOut:
    await _gate(state, ctx)
    _valid_id(client_id)
    try:
        client = await asyncio.to_thread(
            state.agency.update_client,
            client_id,
            ctx.organization_id,
            body.name,
            body.contact_email,
            body.notes,
        )
    except DuplicateClientError as exc:
        raise HTTPException(status_code=409, detail="You already have a client with this name.") from exc
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    await _audit(state, request, ctx, "client.updated", "client", client_id)
    return client


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client(client_id: str, request: Request, state: StateDep, ctx: CanManage) -> Response:
    await _gate(state, ctx)
    _valid_id(client_id)
    if not await asyncio.to_thread(state.agency.delete_client, client_id, ctx.organization_id):
        raise HTTPException(status_code=404, detail="Client not found.")
    await _audit(state, request, ctx, "client.deleted", "client", client_id)
    return Response(status_code=204)


@router.put("/targets/{target_id}/client", status_code=204)
async def assign_client(
    target_id: str, body: AssignClient, request: Request, state: StateDep, ctx: CanManage
) -> Response:
    """Puts a website under a client, or takes it out (client_id null). Both must be in this workspace."""
    await _gate(state, ctx)
    _valid_id(target_id)
    if body.client_id is not None:
        _valid_id(body.client_id)
    if not await asyncio.to_thread(
        state.agency.assign_target, target_id, ctx.organization_id, body.client_id
    ):
        raise HTTPException(status_code=404, detail="Website or client not found.")
    await _audit(state, request, ctx, "client.site_assigned", "target", target_id)
    return Response(status_code=204)


# --- dashboard --------------------------------------------------------------------------------------


def _worst(grades: list[str]) -> str | None:
    known = [g for g in grades if g in GRADE_ORDER]
    return max(known, key=GRADE_ORDER.index) if known else None


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(state: StateDep, ctx: CanRead) -> Dashboard:
    """Per client: its websites and where each stands, from stored completed scans only."""
    await _gate(state, ctx)
    org = ctx.organization_id
    clients = await asyncio.to_thread(state.agency.list_clients, org)
    targets = await asyncio.to_thread(state.agency.targets_with_clients, org)
    latest = await asyncio.to_thread(
        state.agency.latest_completed_scans, org, [t.hostname for t, _ in targets]
    )

    async def site_for(target: TargetRow, client_id: str | None) -> tuple[str | None, DashboardSite]:
        scan_id = latest.get(target.hostname)
        site = DashboardSite(
            target_id=target.id, hostname=target.hostname, verified=target.verified_at is not None
        )
        if scan_id is None:
            return client_id, site
        detail = await asyncio.to_thread(state.repo.get_scan, scan_id, org)
        if detail is None or detail.status is not ScanStatus.COMPLETED:
            return client_id, site
        counts = {s.value: 0 for s in SEVERITY_ORDER}
        for finding in counting_findings(detail):
            if finding.status is FindingStatus.OPEN:
                counts[finding.severity.value] += 1
        site.last_scan_id, site.last_scan_at = detail.id, detail.created_at
        site.score, site.grade = detail.score, detail.grade
        site.open_findings = SeverityCounts(**counts)
        return client_id, site

    placed = await asyncio.gather(*(site_for(t, cid) for t, cid in targets[:200]))
    by_client: dict[str | None, list[DashboardSite]] = {}
    for client_id, site in placed:
        by_client.setdefault(client_id, []).append(site)

    def summarise(client_id: str | None, name: str) -> DashboardClient:
        sites = by_client.get(client_id, [])
        totals = {s.value: sum(getattr(x.open_findings, s.value) for x in sites) for s in SEVERITY_ORDER}
        dates = [x.last_scan_at for x in sites if x.last_scan_at]
        return DashboardClient(
            client_id=client_id,
            name=name,
            sites=sites,
            open_findings=SeverityCounts(**totals),
            worst_grade=_worst([x.grade for x in sites if x.grade]),
            last_scan_at=max(dates) if dates else None,
        )

    rows = [summarise(c.id, c.name) for c in clients]
    if by_client.get(None):
        rows.append(summarise(None, "Not assigned to a client"))
    return Dashboard(clients=rows, total_sites=len(placed), total_clients=len(clients))


# --- branding ---------------------------------------------------------------------------------------


@router.get("/branding", response_model=Branding)
async def get_branding(state: StateDep, ctx: CanRead) -> Branding:
    await _gate(state, ctx)
    return Branding(agency_name=await asyncio.to_thread(state.agency.agency_name, ctx.organization_id))


@router.put("/branding", response_model=Branding)
async def set_branding(body: Branding, request: Request, state: StateDep, ctx: CanManage) -> Branding:
    """The name printed as "Prepared by" on reports made from now on. Existing reports are not changed."""
    await _gate(state, ctx)
    await asyncio.to_thread(state.agency.set_agency_name, ctx.organization_id, body.agency_name)
    await _audit(state, request, ctx, "branding.updated", "organization", ctx.organization_id)
    return body


# --- shared report links (signed-in side) -----------------------------------------------------------


async def _completed_scan(state: StateDep, ctx: OrgContext, scan_id: str) -> ScanDetail:
    _valid_id(scan_id)
    detail = await asyncio.to_thread(state.repo.get_scan, scan_id, ctx.organization_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    if detail.status is not ScanStatus.COMPLETED:
        raise HTTPException(
            status_code=409, detail="A report can be shared once a scan has finished successfully."
        )
    return detail


@router.post("/scans/{scan_id}/shares", response_model=ShareCreated, status_code=201)
async def create_share(
    scan_id: str, body: ShareCreate, request: Request, state: StateDep, ctx: CanShare
) -> ShareCreated:
    await _gate(state, ctx)
    detail = await _completed_scan(state, ctx, scan_id)
    user_id = ctx.principal.user.id
    if not state.report_limiter.check(user_id):
        raise HTTPException(status_code=429, detail="Too many report requests. Try again in a little while.")
    state.report_limiter.record(user_id)
    async with state.report_semaphore:
        try:
            await asyncio.to_thread(state.report_service.ensure_report, detail, ctx.organization_id, user_id)
        except Exception:  # noqa: BLE001 - any rendering fault is reported the same way
            logger.exception("report generation failed", extra={"scan_id": scan_id})
            raise HTTPException(
                status_code=500, detail="The report could not be created. Please try again."
            ) from None
    share, token = await asyncio.to_thread(
        state.agency.create_share, ctx.organization_id, scan_id, user_id, body.days
    )
    await _audit(state, request, ctx, "share.created", "scan", scan_id)
    return ShareCreated(**share.model_dump(), token=token, path=f"/#/shared?token={token}")


@router.get("/scans/{scan_id}/shares", response_model=ShareList)
async def list_shares(scan_id: str, state: StateDep, ctx: CanShare) -> ShareList:
    await _gate(state, ctx)
    _valid_id(scan_id)
    return ShareList(items=await asyncio.to_thread(state.agency.list_shares, ctx.organization_id, scan_id))


@router.delete("/scans/{scan_id}/shares/{share_id}", status_code=204)
async def revoke_share(
    scan_id: str, share_id: str, request: Request, state: StateDep, ctx: CanShare
) -> Response:
    await _gate(state, ctx)
    _valid_id(scan_id)
    _valid_id(share_id)
    if not await asyncio.to_thread(state.agency.revoke_share, share_id, scan_id, ctx.organization_id):
        raise HTTPException(status_code=404, detail="Share link not found.")
    await _audit(state, request, ctx, "share.revoked", "scan", scan_id)
    return Response(status_code=204)


# --- shared report links (public side) --------------------------------------------------------------

_PRIVATE = {
    "Cache-Control": "private, no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


async def _resolve(state: StateDep, request: Request, token: str):  # type: ignore[no-untyped-def]
    """The live share for this link, or the same 404 for anything unknown, revoked or expired."""
    key = client_key(request, state)
    if not state.share_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.", headers=_PRIVATE)
    state.share_limiter.record(key)
    if not (20 <= len(token) <= 100) or not all(c.isalnum() or c in "-_" for c in token):
        raise HTTPException(status_code=404, detail=NOT_FOUND, headers=_PRIVATE)
    found = await asyncio.to_thread(state.agency.resolve_share, token)
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND, headers=_PRIVATE)
    return found


@public_router.get("/{token}", response_model=SharedReportInfo)
async def shared_info(token: str, request: Request, response: Response, state: StateDep) -> SharedReportInfo:
    share, scan, report_id = await _resolve(state, request, token)
    if report_id is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND, headers=_PRIVATE)
    for key, value in _PRIVATE.items():
        response.headers[key] = value
    plan = await state.entitlements.plan_for_async(share.organization_id)
    name = (
        await asyncio.to_thread(state.agency.agency_name, share.organization_id)
        if plan.client_workspace
        else None
    )
    return SharedReportInfo(
        host=scan.host,
        scanned_at=scan.created_at,
        score=scan.score,
        grade=scan.grade,
        prepared_by=name,
        expires_at=share.expires_at,
        download_path=f"/api/v1/shared/{token}/report.pdf",
    )


@public_router.get("/{token}/report.pdf")
async def shared_pdf(token: str, request: Request, state: StateDep) -> Response:
    share, scan, report_id = await _resolve(state, request, token)
    if report_id is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND, headers=_PRIVATE)
    try:
        loaded = await asyncio.to_thread(
            state.report_service.reports.get_file, report_id, share.organization_id
        )
    except ReportIntegrityError:
        logger.error("stored report failed its checksum", extra={"report_id": report_id})
        raise HTTPException(
            status_code=500, detail="This report could not be read.", headers=_PRIVATE
        ) from None
    if loaded is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND, headers=_PRIVATE)
    await asyncio.to_thread(state.agency.record_view, share.id)
    await asyncio.to_thread(
        state.audit.record,
        "share.viewed",
        organization_id=share.organization_id,
        resource_type="scan",
        resource_id=scan.id,
        request_id=request_id(request),
    )
    return Response(
        content=loaded[1],
        media_type="application/pdf",
        headers={**_PRIVATE, "Content-Disposition": f'inline; filename="{report_id}.pdf"'},
    )
