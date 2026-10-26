"""App Scanning (code and dependency checks). A separate module from website scanning.

Everything here answers 404 until SECURESCOPE_APP_SCANNING_ENABLED is on. Uploads are small text manifests sent
as JSON; nothing is executed and the file contents are never stored (only name, size and digest)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError

from app.api.deps import OrgContext, StateDep, request_id, require
from app.appscan import manifests
from app.appscan.pipeline import ScanOutcome, run_dependency_scan
from app.appscan.states import AppScanStatus
from app.billing.errors import PlanLimitError
from app.billing.plans import current_period
from app.models.app_scan import AppScanRow
from app.repositories.appscans import (
    AppProjectNameTaken,
    AppProjectNotFound,
    AppRateLimited,
    IdempotencyKeyReused,
)
from app.schemas.app_scan import (
    AppFindingOut,
    AppInputOut,
    AppOverview,
    AppProjectCreate,
    AppProjectList,
    AppProjectOut,
    AppScanCreate,
    AppScanList,
    AppScanOut,
    AppScanSummary,
    AppUsageOut,
)
from app.security.permissions import Permission

MAX_REQUEST_BYTES = 6 * 1024 * 1024
SCAN_BUDGET_SECONDS = 20.0

LIMITATIONS = [
    "Only the files you upload are checked, and only packages with an exact version can be checked.",
    "A result covers known, published vulnerabilities in the listed packages. It does not review your own code.",
    "No findings means none were found by these checks, not that the application is secure.",
    "Source code is never uploaded or stored: only package names, versions, file names and file digests are kept.",
]

RESULT_TEXT = {
    "queued": "Waiting to start.",
    "running": "Running.",
    "completed_findings": "Completed. Findings were detected.",
    "completed_no_findings": "Completed. No findings were detected by the selected checks.",
    "incomplete": "Incomplete. Some checks could not run or some entries could not be checked.",
    "scanner_error": "Scanner error. Nothing was checked and this run was not counted.",
    "interrupted": "Interrupted before it finished. This run was not counted.",
    "cancelled": "Cancelled.",
}


async def _enabled(state: StateDep) -> None:
    """The feature does not exist for anyone until it is switched on: not even a sign-in is asked for."""
    if not state.settings.app_scanning_enabled:
        raise HTTPException(status_code=404, detail="Not found.")


router = APIRouter(prefix="/app", tags=["app-scanning"], dependencies=[Depends(_enabled)])

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanCreate = Annotated[OrgContext, Depends(require(Permission.SCAN_CREATE))]


def _valid_id(value: str) -> None:
    if not value.isalnum() or len(value) > 64:
        raise HTTPException(status_code=404, detail="Not found.")


async def _audit(state: StateDep, request: Request, ctx: OrgContext, event: str, kind: str, rid: str) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type=kind,
        resource_id=rid,
        request_id=request_id(request),
    )


def _label(status: str, finding_count: int) -> str:
    if status == AppScanStatus.COMPLETED.value:
        return "completed_findings" if finding_count else "completed_no_findings"
    return {
        "queued": "queued",
        "running": "running",
        "incomplete": "incomplete",
        "failed": "scanner_error",
        "interrupted": "interrupted",
        "cancelled": "cancelled",
    }[status]


def _loads(text: str | None, default: object) -> object:
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _counts(severities: list[str]) -> dict[str, int]:
    out = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for severity in severities:
        if severity in out:
            out[severity] += 1
    return out


def _summary(row: AppScanRow, severities: list[str]) -> AppScanSummary:
    label = _label(row.status, len(severities))
    return AppScanSummary(
        id=row.id,
        project_id=row.project_id,
        status=row.status,
        result=label,
        result_text=RESULT_TEXT[label],
        created_at=row.created_at,
        finished_at=row.finished_at,
        counts=_counts(severities),
    )


async def _detail(state: StateDep, organization_id: str, scan_id: str, replayed: bool = False) -> AppScanOut:
    row = await asyncio.to_thread(state.app_scans.get_run, organization_id, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found.")
    stored = await asyncio.to_thread(state.app_scans.get_findings, organization_id, scan_id)
    summary = _summary(row, [f.severity for f in stored])
    return AppScanOut(
        **summary.model_dump(),
        kinds=list(_loads(row.kinds_json, [])),  # type: ignore[call-overload]
        started_at=row.started_at,
        inputs=[AppInputOut(**i) for i in _loads(row.inputs_json, [])],  # type: ignore[attr-defined]
        checks_run=list(_loads(row.checks_run_json, [])),  # type: ignore[call-overload]
        checks_skipped=list(_loads(row.checks_skipped_json, [])),  # type: ignore[call-overload]
        scanners=list(_loads(row.scanners_json, [])),  # type: ignore[call-overload]
        error=row.error,
        findings=[
            AppFindingOut(
                kind=f.kind,
                rule_id=f.rule_id,
                title=f.title,
                severity=f.severity,
                confidence=f.confidence,
                category=f.category,
                description=f.description,
                remediation=f.remediation,
                evidence=f.evidence,
                path=f.path,
                line=f.line,
                ecosystem=f.ecosystem,
                package_name=f.package_name,
                package_version=f.package_version,
                fixed_versions=list(_loads(f.fixed_versions_json, [])),  # type: ignore[call-overload]
                references=list(_loads(f.references_json, [])),  # type: ignore[call-overload]
                aliases=list(_loads(f.aliases_json, [])),  # type: ignore[call-overload]
                fingerprint=f.fingerprint,
            )
            for f in stored
        ],
        limitations=LIMITATIONS,
        replayed=replayed,
    )


async def _read_limited_json(request: Request) -> object:
    """Reads the body without ever holding more than the limit, then parses it. Over the limit: 413."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="The upload is too large.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="The upload is too large.")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status_code=400, detail="The request is not valid JSON.") from exc


# --- overview ------------------------------------------------------------------------------------------


@router.get("/overview", response_model=AppOverview)
async def overview(state: StateDep, ctx: CanRead) -> AppOverview:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    start, end = current_period(datetime.now(UTC))
    usage = await asyncio.to_thread(state.app_scans.usage, ctx.organization_id, start)
    return AppOverview(
        plan=plan.name,
        usage=AppUsageOut(
            runs_used=usage.runs,
            runs_limit=plan.app_scans_per_month,
            projects_used=usage.projects,
            projects_limit=plan.app_projects,
            period_end=end,
        ),
        supported_files=list(manifests.SUPPORTED_FILES),
        max_files=manifests.MAX_FILES_PER_SCAN,
        max_file_bytes=manifests.MAX_FILE_BYTES,
        ci_tokens_available=plan.app_ci_tokens,
        limitations=LIMITATIONS,
    )


# --- projects ------------------------------------------------------------------------------------------


@router.get("/projects", response_model=AppProjectList)
async def list_projects(state: StateDep, ctx: CanRead) -> AppProjectList:
    rows = await asyncio.to_thread(state.app_scans.list_projects, ctx.organization_id)
    return AppProjectList(
        items=[AppProjectOut(id=r.id, name=r.name, source=r.source, created_at=r.created_at) for r in rows]
    )


@router.post("/projects", response_model=AppProjectOut, status_code=201)
async def create_project(
    body: AppProjectCreate, request: Request, state: StateDep, ctx: CanCreate
) -> AppProjectOut:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    try:
        project_id = await asyncio.to_thread(
            state.app_scans.create_project,
            ctx.organization_id,
            ctx.principal.user.id,
            body.name,
            "upload",
            plan.app_projects,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanLimitError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AppProjectNameTaken as exc:
        raise HTTPException(status_code=409, detail="A project with this name already exists.") from exc
    await _audit(state, request, ctx, "app_project.created", "app_project", project_id)
    created = next(
        p
        for p in await asyncio.to_thread(state.app_scans.list_projects, ctx.organization_id)
        if p.id == project_id
    )
    return AppProjectOut(
        id=created.id, name=created.name, source=created.source, created_at=created.created_at
    )


@router.post("/projects/{project_id}/archive", status_code=204)
async def archive_project(project_id: str, request: Request, state: StateDep, ctx: CanCreate) -> None:
    _valid_id(project_id)
    if not await asyncio.to_thread(state.app_scans.archive_project, ctx.organization_id, project_id):
        raise HTTPException(status_code=404, detail="Not found.")
    await _audit(state, request, ctx, "app_project.archived", "app_project", project_id)


# --- scans ---------------------------------------------------------------------------------------------


@router.get("/scans", response_model=AppScanList)
async def list_scans(state: StateDep, ctx: CanRead, project_id: str | None = None) -> AppScanList:
    if project_id is not None:
        _valid_id(project_id)
    rows = await asyncio.to_thread(state.app_scans.list_runs, ctx.organization_id, project_id)
    return AppScanList(items=[_summary(row, severities) for row, severities in rows])


@router.get("/scans/{scan_id}", response_model=AppScanOut)
async def get_scan(scan_id: str, state: StateDep, ctx: CanRead) -> AppScanOut:
    _valid_id(scan_id)
    return await _detail(state, ctx.organization_id, scan_id)


@router.post("/scans", response_model=AppScanOut, status_code=201)
async def create_scan(
    request: Request,
    state: StateDep,
    ctx: CanCreate,
    idempotency_key: Annotated[str | None, Header(max_length=80)] = None,
) -> AppScanOut:
    raw = await _read_limited_json(request)
    try:
        body = AppScanCreate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail="The request is not valid: check the project, files and checks."
        ) from exc

    # 1. Read the files. Anything unreadable is refused here, before a run exists, so it is never counted.
    names = [f.name for f in body.files]
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="Each file may be uploaded once.")
    parsed: list[manifests.ParseResult] = []
    for f in body.files:
        try:
            parsed.append(
                await asyncio.to_thread(manifests.parse_manifest, f.name, f.content.encode("utf-8"))
            )
        except manifests.ManifestError as exc:
            raise HTTPException(
                status_code=422, detail={"code": exc.code, "message": str(exc), "file": f.name[:64]}
            ) from exc
    if sum(len(r.packages) for r in parsed) == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_packages",
                "message": "No checkable packages were found in the files.",
                "file": "",
            },
        )

    # 2. Accept the run. This is the one place a run is counted.
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    start, _ = current_period(datetime.now(UTC))
    inputs: list[dict[str, object]] = [
        {"name": r.file_name, "size": r.size, "sha256": r.sha256} for r in parsed
    ]
    try:
        accepted = await asyncio.to_thread(
            state.app_scans.accept_run,
            ctx.organization_id,
            body.project_id,
            ctx.principal.user.id,
            list(body.kinds),
            inputs,
            plan.app_scans_per_month,
            start,
            state.settings.app_scans_per_project_per_hour,
            idempotency_key,
            body.ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanLimitError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AppRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AppProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    except IdempotencyKeyReused as exc:
        raise HTTPException(
            status_code=409, detail="This idempotency key was used for another project."
        ) from exc
    if accepted.replay:
        return await _detail(state, ctx.organization_id, accepted.scan_id, replayed=True)
    await _audit(state, request, ctx, "app_scan.created", "app_scan", accepted.scan_id)

    # 3. Run it. One at a time on this instance; a stopped request leaves the run marked interrupted.
    scan_id = accepted.scan_id
    try:
        async with state.app_scan_semaphore:
            await asyncio.to_thread(state.app_scans.start_run, ctx.organization_id, scan_id)
            try:
                outcome = await asyncio.to_thread(
                    run_dependency_scan, body.project_id, parsed, state.app_source, SCAN_BUDGET_SECONDS
                )
            except Exception:  # a defect must end the run honestly, never leave it running or leak details
                outcome = ScanOutcome(status=AppScanStatus.FAILED, error="The scan could not be completed.")
            await asyncio.to_thread(state.app_scans.store_result, ctx.organization_id, scan_id, outcome)
    except asyncio.CancelledError:
        await asyncio.shield(
            asyncio.to_thread(
                state.app_scans.finish_run,
                ctx.organization_id,
                scan_id,
                AppScanStatus.INTERRUPTED,
                "The request ended before the scan finished.",
            )
        )
        raise
    await _audit(state, request, ctx, "app_scan.finished", "app_scan", scan_id)
    return await _detail(state, ctx.organization_id, scan_id)
