from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response

from app.api.deps import StateDep
from app.api.v1 import (
    account,
    agency,
    analytics,
    audit,
    auth,
    findings,
    invitations,
    oauth,
    organizations,
    overview,
    scans,
    schedules,
    targets,
)
from app.schemas.scan import HealthResponse

VERSION = "0.11.0"
logger = logging.getLogger("securescope.api")

router = APIRouter(prefix="/api/v1")


# HEAD as well as GET: uptime monitors check with HEAD by default.
@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(version=VERSION)


@router.api_route("/ready", methods=["GET", "HEAD"], tags=["health"])
async def ready(state: StateDep, response: Response) -> dict[str, str]:
    """Readiness: the database must answer. No internals are exposed."""
    try:
        await asyncio.to_thread(state.repo.ping)
    except Exception:
        logger.warning("readiness check failed", exc_info=True)
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ready"}


router.include_router(auth.router)
router.include_router(account.router)
router.include_router(oauth.router)
router.include_router(organizations.router)
router.include_router(invitations.router)
router.include_router(scans.router)
router.include_router(targets.router)
router.include_router(findings.router)
router.include_router(overview.router)
router.include_router(audit.router)
router.include_router(analytics.router)
router.include_router(agency.router)
router.include_router(agency.public_router)
router.include_router(schedules.router)
router.include_router(schedules.internal_router)
