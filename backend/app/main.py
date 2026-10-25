"""SecureScope API application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import SAFE_METHODS, AppState
from app.api.v1 import VERSION
from app.api.v1 import router as v1_router
from app.api.v1.monitoring import router as monitoring_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, log_event
from app.services.mailer import Mailer

logger = logging.getLogger("securescope.api")

API_CSP = "default-src 'none'; frame-ancestors 'none'"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")

__all__ = ["VERSION", "create_app"]


MAINTENANCE_INTERVAL_SECONDS = 3600


async def _maintenance_step(name: str, function: Callable[..., Any], *args: Any) -> Any:
    """Runs one clean-up step. A failure (for example a database that is still waking up) is logged and the next
    step still runs; one bad step must never stop the others or end the loop."""
    try:
        return await asyncio.to_thread(function, *args)
    except Exception:
        logger.exception("maintenance step failed: %s", name)
        return None


async def _maintenance_loop(state: AppState) -> None:
    while True:
        if state.settings.admin_email:
            await _maintenance_step(
                "internal plan", state.plans.assign_internal_to_operator, state.settings.admin_email
            )
        removed = await _maintenance_step("history retention", state.repo.delete_expired_history)
        if removed:
            log_event(logger, "retention cleanup", removed=removed)
        await _maintenance_step("expired challenges", state.targets.purge_expired_challenges)
        await _maintenance_step("old webhook retries", state.webhook_repo.purge_old_retries)
        await _maintenance_step("expired sessions", state.accounts.purge_expired_sessions)
        await _maintenance_step("expired sign-in states", state.accounts.purge_expired_oauth_states)
        await _maintenance_step("old invitations", state.accounts.purge_old_invitations)
        await _maintenance_step(
            "analytics retention", state.analytics.delete_older_than, state.settings.analytics_retention_days
        )
        audit_removed = await _maintenance_step(
            "audit retention", state.audit.delete_older_than, state.settings.audit_retention_days
        )
        if audit_removed:
            log_event(logger, "audit retention cleanup", removed=audit_removed)
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)


def _route_template(request: Request) -> str:
    """The matched route's path with each parameter value replaced by its name, or "unmatched".

    Built from the request path rather than the route object, because a route inside nested routers
    reports its path without the /api/v1 prefix."""
    if request.scope.get("route") is None:
        return "unmatched"
    path = request.url.path
    for name, value in request.path_params.items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path


def _measure(request: Request, status: int, started: float) -> None:
    """Feeds the Platform Health numbers. Labels are route templates, never raw paths."""
    state = getattr(request.app.state, "s", None)
    if state is None:
        return
    template = _route_template(request)
    state.metrics.record(template, request.method, status, time.perf_counter() - started)


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(settings, mailer)
        interrupted = await asyncio.to_thread(state.repo.fail_interrupted)
        if interrupted:
            log_event(logger, "marked interrupted scans as failed", count=interrupted)
        app.state.s = state
        cleaner = asyncio.create_task(_maintenance_loop(state))
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
        docs_url="/api/docs" if settings.api_docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.api_docs_enabled else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Organization-Id", "Idempotency-Key"],
        max_age=600,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_failed(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Name the field and the problem, but never send the submitted value back: it may be a password.
        problems = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": problems}, status_code=422)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = supplied if REQUEST_ID_RE.match(supplied) else uuid.uuid4().hex
        # Browsers always send Origin on cross-site unsafe requests; reject unknown origins outright.
        started = time.perf_counter()
        origin = request.headers.get("origin")
        if request.method not in SAFE_METHODS and origin and origin not in settings.cors_origins:
            response: Response = JSONResponse({"detail": "Cross-origin request rejected."}, status_code=403)
        else:
            try:
                response = await call_next(request)
            except Exception:
                _measure(request, 500, started)
                raise
        _measure(request, response.status_code, started)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(v1_router)
    app.include_router(monitoring_router)
    return app
