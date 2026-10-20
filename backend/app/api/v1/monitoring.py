"""Platform Health for the operator, plus the Prometheus scrape endpoint."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response

from app.api.deps import AdminDep, AppState, StateDep
from app.schemas.health import (
    Configuration,
    DatabaseHealth,
    MailHealth,
    PlatformHealth,
    RequestWindow,
    ScanHealth,
)
from app.security.tokens import constant_time_equal
from app.services.mailer import ApiMailer

router = APIRouter(tags=["platform"])
VERSION_PLACEHOLDER = "unknown"


def _db_check(state: AppState) -> tuple[bool, int | None]:
    started = time.perf_counter()
    try:
        state.repo.ping()
    except Exception:
        return False, None
    return True, round((time.perf_counter() - started) * 1000)


def _mail(state: AppState) -> MailHealth:
    mailer = state.auth.mailer
    provider = state.settings.mail_provider
    if isinstance(mailer, ApiMailer):
        stats = mailer.stats
        return MailHealth(
            provider=provider,
            delivering=True,
            sent=stats.sent,
            failed=stats.failed,
            last_success_at=stats.last_success_at,
            last_failure_at=stats.last_failure_at,
            last_failure_status=stats.last_failure_status,
        )
    # The development mailer only writes to the log: no real email leaves the system.
    return MailHealth(
        provider=provider,
        delivering=False,
        sent=0,
        failed=0,
        last_success_at=None,
        last_failure_at=None,
        last_failure_status=None,
    )


@router.get("/api/v1/platform/health", response_model=PlatformHealth)
async def platform_health(_admin: AdminDep, state: StateDep) -> PlatformHealth:
    from app.api.v1 import VERSION

    ok, latency = await asyncio.to_thread(_db_check, state)
    since = datetime.now(UTC) - timedelta(hours=24)
    scan_stats: dict[str, object] = {"counts": {}, "active": 0, "avg_seconds": None}
    if ok:
        scan_stats = await asyncio.to_thread(state.repo.stats_since, since)
    counts: dict[str, int] = scan_stats["counts"]  # type: ignore[assignment]
    settings = state.settings
    return PlatformHealth(
        version=VERSION,
        started_at=datetime.fromtimestamp(state.metrics.started_at, UTC),
        uptime_seconds=state.metrics.uptime_seconds,
        database=DatabaseHealth(ok=ok, latency_ms=latency),
        requests=RequestWindow(**state.metrics.window()),
        scans=ScanHealth(
            window_hours=24,
            completed=counts.get("completed", 0),
            failed=counts.get("failed", 0),
            cancelled=counts.get("cancelled", 0),
            in_progress=int(scan_stats["active"]),  # type: ignore[call-overload]
            avg_seconds=scan_stats["avg_seconds"],
            max_concurrent=settings.max_concurrent_scans,
            running_here=state.pending,
        ),
        mail=_mail(state),
        configuration=Configuration(
            trusted_proxy=settings.trusted_proxy_secret is not None,
            admin_email=bool(settings.admin_email),
            analytics_enabled=settings.analytics_enabled,
            metrics_endpoint=settings.metrics_token is not None,
            cookie_secure=settings.cookie_secure,
            verification_valid_days=settings.target_verification_valid_days,
            retention_days=settings.retention_days,
        ),
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(
    state: StateDep, authorization: Annotated[str, Header()] = ""
) -> Response:
    """Prometheus text format. Needs `Authorization: Bearer <SECURESCOPE_METRICS_TOKEN>`; without a
    configured token the endpoint does not exist."""
    token = state.settings.metrics_token
    if token is None:
        raise HTTPException(status_code=404, detail="Not found.")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not constant_time_equal(supplied.strip(), token.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid or missing token.", headers={"WWW-Authenticate": "Bearer"})
    ok, latency = await asyncio.to_thread(_db_check, state)
    lines = [
        "# HELP securescope_up 1 while the API process is serving requests.",
        "# TYPE securescope_up gauge",
        "securescope_up 1",
        "# HELP securescope_process_start_time_seconds Start time of this process, Unix seconds.",
        "# TYPE securescope_process_start_time_seconds gauge",
        f"securescope_process_start_time_seconds {state.metrics.started_at:.0f}",
        "# HELP securescope_database_up 1 if the database answered a trivial query just now.",
        "# TYPE securescope_database_up gauge",
        f"securescope_database_up {1 if ok else 0}",
    ]
    if latency is not None:
        lines += [
            "# TYPE securescope_database_ping_seconds gauge",
            f"securescope_database_ping_seconds {latency / 1000:.4f}",
        ]
    lines += state.metrics.prometheus()
    if ok:
        stats = await asyncio.to_thread(
            state.repo.stats_since, datetime.now(UTC) - timedelta(hours=24)
        )
        counts: dict[str, int] = stats["counts"]  # type: ignore[assignment]
        lines += [
            "# HELP securescope_scans_24h Scans created in the last 24 hours, by status.",
            "# TYPE securescope_scans_24h gauge",
        ]
        for status in ("completed", "failed", "cancelled", "queued", "running"):
            lines.append(f'securescope_scans_24h{{status="{status}"}} {counts.get(status, 0)}')
    lines += [
        "# HELP securescope_scans_running_here Scan tasks running inside this process.",
        "# TYPE securescope_scans_running_here gauge",
        f"securescope_scans_running_here {state.pending}",
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
