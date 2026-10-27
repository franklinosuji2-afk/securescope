"""App Scanning (code and dependency checks). A separate module from website scanning.

Everything here answers 404 until SECURESCOPE_APP_SCANNING_ENABLED is on. Uploads are small text manifests sent
as JSON; nothing is executed and the file contents are never stored (only name, size and digest)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import EllipsisType
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError

from app.api.deps import OrgContext, StateDep, organization_context, request_id, require
from app.api.v1.ci import CiActor, bearer_actor
from app.appscan import manifests
from app.appscan.pipeline import ScanOutcome, run_dependency_scan
from app.appscan.states import AppScanStatus
from app.appscan.submission import (
    MAX_DOCUMENT_BYTES,
    Submission,
    SubmissionRejected,
    build_outcome,
    parse_submission,
)
from app.billing.errors import PlanLimitError
from app.billing.plans import current_period
from app.models.app_scan import AppScanRow
from app.repositories.appscans import (
    AcceptedRun,
    AppProjectNameTaken,
    AppProjectNotFound,
    AppRateLimited,
    IdempotencyKeyReused,
    TokenNoLongerValid,
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

logger = logging.getLogger("securescope.appscans")
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


async def _listed_workspace(
    state: StateDep, ctx: Annotated[OrgContext, Depends(organization_context)]
) -> OrgContext:
    """The pilot allow-list: a workspace that is not on it gets the answer of a feature that is switched off. This
    runs before the role check, so nothing about the feature is told to a workspace that may not use it."""
    if not state.settings.app_scanning_allows(ctx.organization_id):
        raise HTTPException(status_code=404, detail="Not found.")
    return ctx


CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ, _listed_workspace))]
CanCreate = Annotated[OrgContext, Depends(require(Permission.SCAN_CREATE, _listed_workspace))]


def _valid_id(value: str) -> None:
    if not value.isalnum() or len(value) > 64:
        raise HTTPException(status_code=404, detail="Not found.")


async def _audit_as(
    state: StateDep, request: Request, organization_id: str, user_id: str, event: str, kind: str, rid: str
) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=organization_id,
        actor_user_id=user_id,
        resource_type=kind,
        resource_id=rid,
        request_id=request_id(request),
    )


async def _audit(state: StateDep, request: Request, ctx: OrgContext, event: str, kind: str, rid: str) -> None:
    await _audit_as(state, request, ctx.organization_id, ctx.principal.user.id, event, kind, rid)


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


BODY_READ_SECONDS: float = 30
# Checking a document (JSON, then the secret check) is CPU work. At most one runs at a time per instance, a request
# waits a short while for its turn, and one that takes too long is refused. The thread cannot be killed, so its
# slot is only freed when the thread has really finished (see `_run_exclusive`).
CHECK_WAIT_SECONDS: float = 10
CHECK_RUN_SECONDS: float = 20
# A browser scan stops itself after SCAN_BUDGET_SECONDS, but a lookup in progress cannot be interrupted, so a hard
# limit sits above it. Past it the run ends Failed (not counted); the thread still keeps its slot until it returns.
SCAN_HARD_SECONDS: float = 60
CI_KEY_PREFIX = "ci:"


class SlotTimeout(Exception):
    """The work took longer than allowed. The worker thread may still be running and still holds its slot."""


async def _run_exclusive[T](
    state: StateDep,
    function: Callable[..., T],
    *args: object,
    wait_seconds: float | None | EllipsisType = ...,
    run_seconds: float | None | EllipsisType = ...,
) -> T:
    """Runs `function` in a worker thread while holding one processing slot, and gives the slot back only when the
    thread has finished, even if the request is cancelled or times out meanwhile (a thread cannot be stopped, so
    letting go of the slot earlier would allow more threads than the limit). Used by every App Scanning route that
    does CPU-heavy work. `...` means the check defaults above; `None` means no limit (a cancelled wait takes no
    slot)."""
    if wait_seconds is ...:
        wait_seconds = CHECK_WAIT_SECONDS
    if run_seconds is ...:
        run_seconds = CHECK_RUN_SECONDS
    semaphore = state.app_scan_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), wait_seconds)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=503, detail="Busy. Try again shortly.", headers={"Retry-After": "30"}
        ) from exc
    task: asyncio.Future[T] = asyncio.ensure_future(asyncio.to_thread(function, *args))

    def finished(done: asyncio.Future[T]) -> None:
        semaphore.release()
        if not done.cancelled():
            done.exception()  # mark any error as seen; the waiting request reports it

    task.add_done_callback(finished)
    try:
        return await asyncio.wait_for(asyncio.shield(task), run_seconds)
    except TimeoutError as exc:
        raise SlotTimeout from exc


async def _read_body(request: Request, limit: int) -> bytes:
    """Reads the body without ever holding more than `limit` bytes. Over the limit: 413, before any parsing."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail="The upload is too large.")
    chunks: list[bytes] = []
    total = 0
    try:
        async with asyncio.timeout(BODY_READ_SECONDS):  # a slow sender cannot hold a connection open for ever
            async for chunk in request.stream():
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="The upload is too large.")
                chunks.append(chunk)
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail="The upload took too long.") from exc
    return b"".join(chunks)


def _parse_document(raw: bytes) -> Submission:
    return parse_submission(_parse_json(raw))


class CheckFailed(Exception):
    """The worker failed for a reason that is not the submitter's. Carries no text: whatever the original error
    said could contain part of the document."""


def _scan_job(
    state: Any, organization_id: str, scan_id: str, project_id: str, parsed: list[manifests.ParseResult]
) -> ScanOutcome | None:
    """The CPU and lookup work of a browser scan, in a worker thread that holds a processing slot. Returns the
    result to store, or None when the run was already ended (for example the request was cancelled while it
    waited for a slot), in which case nothing is scanned."""
    if not state.app_scans.start_run(organization_id, scan_id):
        return None
    try:
        return run_dependency_scan(project_id, parsed, state.app_source, SCAN_BUDGET_SECONDS)
    except Exception:  # a defect must end the run honestly, never leave it running or leak details
        return ScanOutcome(status=AppScanStatus.FAILED, error="The scan could not be completed.")


def _check_document(raw: bytes) -> tuple[Submission, ScanOutcome]:
    """All the CPU-heavy work on a submission, done before anything is stored or counted: reading the JSON, the
    secret check, the strict schema, and turning it into the result to store (which cleans every text again)."""
    try:
        submission = _parse_document(raw)
        try:
            outcome = build_outcome(submission)
        except Exception:  # a defect in building the result ends the run honestly, and leaks nothing
            outcome = ScanOutcome(status=AppScanStatus.FAILED, error="The submission could not be processed.")
        return submission, outcome
    except (SubmissionRejected, HTTPException):
        raise
    except Exception as exc:
        logger.warning("an app scanning submission could not be checked (%s)", type(exc).__name__)
        raise CheckFailed from None


def _parse_json(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status_code=400, detail="The request is not valid JSON.") from exc


async def _read_limited_json(request: Request) -> object:
    return _parse_json(await _read_body(request, MAX_REQUEST_BYTES))


async def _accept(
    state: StateDep,
    organization_id: str,
    project_id: str,
    user_id: str,
    kinds: list[str],
    inputs: list[dict[str, object]],
    monthly_limit: int | None,
    period_start: datetime,
    idempotency_key: str | None,
    ref: str | None,
    token_id: str | None = None,
) -> AcceptedRun:
    """The one place a run is accepted and counted, for browser uploads and CI submissions alike."""
    try:
        return await asyncio.to_thread(
            state.app_scans.accept_run,
            organization_id,
            project_id,
            user_id,
            kinds,
            inputs,
            monthly_limit,
            period_start,
            state.settings.app_scans_per_project_per_hour,
            idempotency_key,
            ref,
            token_id,
            state.settings.app_ci_submissions_per_token_per_hour if token_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanLimitError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AppRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AppProjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc
    except TokenNoLongerValid as exc:
        raise HTTPException(status_code=401, detail=REFUSED_CALLER) from exc
    except IdempotencyKeyReused as exc:
        raise HTTPException(
            status_code=409, detail="This idempotency key was used for another project."
        ) from exc


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
    if idempotency_key is not None and idempotency_key.startswith(CI_KEY_PREFIX):
        # That namespace belongs to CI submissions, so the two kinds of key can never meet.
        raise HTTPException(status_code=422, detail="This Idempotency-Key is not allowed.")
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
    accepted = await _accept(
        state,
        ctx.organization_id,
        body.project_id,
        ctx.principal.user.id,
        list(body.kinds),
        inputs,
        plan.app_scans_per_month,
        start,
        idempotency_key,
        body.ref,
    )
    if accepted.replay:
        return await _detail(state, ctx.organization_id, accepted.scan_id, replayed=True)
    await _audit(state, request, ctx, "app_scan.created", "app_scan", accepted.scan_id)

    # 3. Run it. One at a time on this instance. The worker thread only computes the result; storing it is a
    # separate, atomic step done here, so a stopped, cancelled or timed-out request can never leave partial
    # findings or a completed run behind: it ends Interrupted or Failed, and neither is counted.
    scan_id = accepted.scan_id
    try:
        try:
            outcome = await _run_exclusive(
                state,
                _scan_job,
                state,
                ctx.organization_id,
                scan_id,
                body.project_id,
                parsed,
                wait_seconds=None,
                run_seconds=SCAN_HARD_SECONDS,
            )
        except SlotTimeout:
            outcome = ScanOutcome(
                status=AppScanStatus.FAILED, error="The scan took too long and was stopped."
            )
        if outcome is not None:
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


# --- CI submissions (results of tools the customer ran on their own runner) ----------------------------------------

REFUSED_CALLER = "The API token is not valid, or it has been removed."


async def app_ci_actor(
    request: Request, state: StateDep, authorization: Annotated[str | None, Header()] = None
) -> CiActor:
    """A bearer token of App Scanning scope, from a member who may still start scans, in a workspace whose plan
    still includes App Scanning CI access. Anything else gets the same 401."""
    actor = await bearer_actor(request, state, authorization, "app")
    if not state.settings.app_scanning_allows(actor.organization_id):
        raise HTTPException(status_code=404, detail="Not found.")
    plan = await state.entitlements.plan_for_async(actor.organization_id)
    if not plan.app_ci_tokens:
        raise HTTPException(status_code=401, detail=REFUSED_CALLER)
    return actor


@router.post("/ci/submissions", response_model=AppScanOut, status_code=201)
async def submit_ci_results(
    request: Request,
    state: StateDep,
    actor: Annotated[CiActor, Depends(app_ci_actor)],
    idempotency_key: Annotated[str | None, Header(max_length=70)] = None,
) -> AppScanOut:
    if not idempotency_key:
        raise HTTPException(
            status_code=400, detail="Send an Idempotency-Key header (for example your pipeline run id)."
        )
    # Size first, then structure, then secrets, all before anything is stored or counted.
    raw = await _read_body(request, MAX_DOCUMENT_BYTES)
    try:
        # Reading a large document (JSON, the secret check over every string, building the result) is real work:
        # it runs in a worker thread, one at a time per instance, before anything is stored or counted, so a
        # busy answer, a timeout or a cancelled request leaves no run behind.
        submission, outcome = await _run_exclusive(state, _check_document, raw)
    except SubmissionRejected as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    except SlotTimeout:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "too_complex",
                "message": "The submission took too long to check and was refused.",
            },
        ) from None
    except CheckFailed:
        raise HTTPException(status_code=500, detail="The submission could not be checked.") from None

    plan = await state.entitlements.plan_for_async(actor.organization_id)
    start, _ = current_period(datetime.now(UTC))
    inputs: list[dict[str, object]] = [
        {"name": "ci-submission", "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    ]
    kinds: list[str] = sorted({c.kind for c in submission.checks})
    accepted = await _accept(
        state,
        actor.organization_id,
        submission.project_id,
        actor.user_id,
        kinds,
        inputs,
        plan.app_scans_per_month,
        start,
        f"{CI_KEY_PREFIX}{idempotency_key}",
        submission.ref or None,
        actor.token_id,
    )
    if accepted.replay:
        return await _detail(state, actor.organization_id, accepted.scan_id, replayed=True)
    scan_id = accepted.scan_id
    try:
        # Only database work is left: the run is recorded, then the already-built result is stored.
        await _audit_as(
            state, request, actor.organization_id, actor.user_id, "app_scan.submitted", "app_scan", scan_id
        )
        await asyncio.to_thread(state.app_scans.start_run, actor.organization_id, scan_id)
        await asyncio.to_thread(state.app_scans.store_result, actor.organization_id, scan_id, outcome)
    except asyncio.CancelledError:
        await asyncio.shield(
            asyncio.to_thread(
                state.app_scans.finish_run,
                actor.organization_id,
                scan_id,
                AppScanStatus.INTERRUPTED,
                "The request ended before the submission was processed.",
            )
        )
        raise
    except Exception:
        # Whatever went wrong, the run must not stay queued or running; it ends Failed and is not counted.
        await asyncio.shield(
            asyncio.to_thread(
                state.app_scans.finish_run,
                actor.organization_id,
                scan_id,
                AppScanStatus.FAILED,
                "The submission could not be processed.",
            )
        )
        raise
    await _audit_as(
        state, request, actor.organization_id, actor.user_id, "app_scan.finished", "app_scan", scan_id
    )
    return await _detail(state, actor.organization_id, scan_id)
