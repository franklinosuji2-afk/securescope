"""SecureScope API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, log_event
from app.database.session import make_engine
from app.middleware.ratelimit import SlidingWindowLimiter
from app.reporting import reports
from app.repositories.scans import ScanRepository
from app.scanner.runner import execute_scan
from app.schemas.scan import (
    HealthResponse,
    ScanCreate,
    ScanDetail,
    ScanList,
    ScanStatus,
)
from app.security.target import TargetError, validate_target

VERSION = "0.2.0"
logger = logging.getLogger("securescope.api")

API_CSP = "default-src 'none'; frame-ancestors 'none'"
REPORT_HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = make_engine(settings.database_url)
        self.repo = ScanRepository(self.engine)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_scans)
        self.client_limiter = SlidingWindowLimiter(settings.scans_per_client_per_hour)
        self.target_limiter = SlidingWindowLimiter(settings.scans_per_target_per_hour)
        self.tasks: set[asyncio.Task[None]] = set()

    @property
    def pending(self) -> int:
        return len(self.tasks)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.s
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def client_key(request: Request, state: AppState) -> str:
    if state.settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _retention_loop(state: AppState) -> None:
    while True:
        removed = await asyncio.to_thread(state.repo.delete_older_than, state.settings.retention_days)
        if removed:
            log_event(logger, "retention cleanup", removed=removed)
        await asyncio.sleep(3600)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(settings)
        interrupted = await asyncio.to_thread(state.repo.fail_interrupted)
        if interrupted:
            log_event(logger, "marked interrupted scans as failed", count=interrupted)
        app.state.s = state
        cleaner = asyncio.create_task(_retention_loop(state))
        try:
            yield
        finally:
            cleaner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleaner
            for task in list(state.tasks):
                task.cancel()
            state.engine.dispose()

    app = FastAPI(
        title="SecureScope API",
        version=VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    router = APIRouter(prefix="/api/v1")

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=VERSION)

    @router.get("/ready")
    async def ready(state: StateDep, response: Response) -> dict[str, str]:
        """Readiness: the database must answer. No internals are exposed."""
        try:
            await asyncio.to_thread(state.repo.ping)
        except Exception:
            logger.warning("readiness check failed", exc_info=True)
            response.status_code = 503
            return {"status": "unavailable"}
        return {"status": "ready"}

    @router.post("/scans", response_model=ScanDetail, status_code=202)
    async def create_scan(body: ScanCreate, request: Request, state: StateDep) -> ScanDetail:
        if not body.authorization_confirmed:
            raise HTTPException(
                status_code=400,
                detail="You must confirm that you own this target or have written authorization to test it.",
            )
        try:
            target = await validate_target(body.url, state.settings)
        except TargetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        client = client_key(request, state)
        if not state.client_limiter.check(client):
            raise HTTPException(status_code=429, detail="Too many scans from your address. Try again later.")
        if not state.target_limiter.check(target.host):
            raise HTTPException(
                status_code=429, detail="This target was scanned too often recently. Try again later."
            )
        if state.pending >= state.settings.max_concurrent_scans * 4:
            raise HTTPException(status_code=429, detail="The scanner is busy. Try again in a minute.")
        state.client_limiter.record(client)
        state.target_limiter.record(target.host)

        scan_id = await asyncio.to_thread(state.repo.create_scan, target.url, target.host)
        task = asyncio.create_task(
            execute_scan(scan_id, target.url, target.host, state.settings, state.repo, state.semaphore)
        )
        state.tasks.add(task)
        task.add_done_callback(state.tasks.discard)
        log_event(logger, "scan queued", scan_id=scan_id, host=target.host)
        detail = await asyncio.to_thread(state.repo.get_scan, scan_id)
        assert detail is not None
        return detail

    @router.get("/scans", response_model=ScanList)
    async def list_scans(
        state: StateDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ScanList:
        items, total = await asyncio.to_thread(state.repo.list_scans, limit, offset)
        return ScanList(items=items, total=total)

    async def load(state: AppState, scan_id: str) -> ScanDetail:
        if not scan_id.isalnum() or len(scan_id) > 64:
            raise HTTPException(status_code=404, detail="Scan not found.")
        detail = await asyncio.to_thread(state.repo.get_scan, scan_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        return detail

    @router.get("/scans/{scan_id}", response_model=ScanDetail)
    async def get_scan(scan_id: str, state: StateDep) -> ScanDetail:
        return await load(state, scan_id)

    @router.get("/scans/{scan_id}/report")
    async def export_report(
        scan_id: str,
        state: StateDep,
        format: Literal["json", "md", "html"] = "json",  # noqa: A002
    ) -> Response:
        detail = await load(state, scan_id)
        if detail.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
            raise HTTPException(status_code=409, detail="The scan has not finished yet.")
        media, extension, content = {
            "json": ("application/json", "json", reports.to_json),
            "md": ("text/markdown; charset=utf-8", "md", reports.to_markdown),
            "html": ("text/html; charset=utf-8", "html", reports.to_html),
        }[format]
        headers = {
            "Content-Disposition": f'attachment; filename="{reports.safe_filename(detail, extension)}"'
        }
        if format == "html":
            headers["Content-Security-Policy"] = REPORT_HTML_CSP
        return Response(content=content(detail), media_type=media, headers=headers)

    app.include_router(router)
    return app
