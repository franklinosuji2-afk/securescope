"""Finding triage: analysts record what the organization decided about a finding on a host."""

from __future__ import annotations

import asyncio
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import OrgContext, StateDep, request_id, require
from app.schemas.scan import FindingStatusUpdate
from app.security.permissions import Permission

router = APIRouter(prefix="/findings", tags=["findings"])
CanTriage = Annotated[OrgContext, Depends(require(Permission.FINDING_TRIAGE))]
FINGERPRINT = re.compile(r"^[0-9a-f]{32}$")


@router.patch("/{fingerprint}", status_code=204)
async def set_status(
    fingerprint: str, body: FindingStatusUpdate, request: Request, state: StateDep, ctx: CanTriage
) -> Response:
    if not FINGERPRINT.match(fingerprint):
        raise HTTPException(status_code=404, detail="Finding not found.")
    found = await asyncio.to_thread(
        state.repo.set_finding_status,
        ctx.organization_id,
        fingerprint,
        body.status,
        body.note,
        ctx.principal.user.id,
    )
    if not found:  # also returned for findings of other organizations
        raise HTTPException(status_code=404, detail="Finding not found.")
    await asyncio.to_thread(
        state.audit.record,
        "finding.status_changed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="finding",
        resource_id=fingerprint,
        request_id=request_id(request),
    )
    return Response(status_code=204)
