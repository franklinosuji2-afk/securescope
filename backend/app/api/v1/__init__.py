from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response

from app.api.deps import StateDep
from app.api.v1 import auth, organizations, scans, targets
from app.schemas.scan import HealthResponse

VERSION = "0.4.0"
logger = logging.getLogger("securescope.api")

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(version=VERSION)


@router.get("/ready", tags=["health"])
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
router.include_router(organizations.router)
router.include_router(scans.router)
router.include_router(targets.router)
