from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import OrgContext, StateDep, require
from app.schemas.audit import AuditList
from app.security.permissions import Permission

router = APIRouter(prefix="/audit-events", tags=["audit"])

# Owners and admins only: the log names members and shows what each of them did.
CanReadAudit = Annotated[OrgContext, Depends(require(Permission.AUDIT_READ))]


@router.get("", response_model=AuditList)
async def list_audit_events(
    state: StateDep,
    ctx: CanReadAudit,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: Annotated[str | None, Query(pattern=r"^[a-z_.]{1,48}$")] = None,
) -> AuditList:
    items, total = await asyncio.to_thread(
        state.audit.query_events, ctx.organization_id, limit=limit, offset=offset, event_type=event_type
    )
    event_types = await asyncio.to_thread(state.audit.event_types, ctx.organization_id)
    return AuditList(items=items, total=total, event_types=event_types)
