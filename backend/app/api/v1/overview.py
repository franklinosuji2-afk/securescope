"""Overview: where each recently scanned site stands, in one request."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import OrgContext, StateDep, require
from app.schemas.scan import Overview
from app.security.permissions import Permission

router = APIRouter(prefix="/overview", tags=["overview"])
CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]


@router.get("", response_model=Overview)
async def get_overview(state: StateDep, ctx: CanRead) -> Overview:
    return await asyncio.to_thread(state.repo.overview, ctx.organization_id)
