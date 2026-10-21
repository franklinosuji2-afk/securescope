"""Looking at and accepting an invitation that arrived by email."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import PrincipalDep, StateDep, client_key, request_id
from app.schemas.auth import InvitationAccept, InvitationAccepted, InvitationPreview

router = APIRouter(prefix="/invitations", tags=["invitations"])

NO_LONGER_VALID = "This invitation is no longer valid. Ask the person who invited you to send a new one."


def _limit(state: StateDep, request: Request) -> None:
    key = client_key(request, state)
    if not state.invite_link_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")
    state.invite_link_limiter.record(key)


@router.get("/preview", response_model=InvitationPreview)
async def preview_invitation(
    request: Request,
    state: StateDep,
    token: Annotated[str, Query(min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")],
) -> InvitationPreview:
    """What the link is for, shown before anyone signs in. The token is the only secret needed."""
    _limit(state, request)
    record = await asyncio.to_thread(state.accounts.open_invitation, token)
    if record is None:
        raise HTTPException(status_code=404, detail=NO_LONGER_VALID)
    return InvitationPreview(organization_name=record.organization_name, email=record.email, role=record.role)


@router.post("/accept", response_model=InvitationAccepted)
async def accept_invitation(
    body: InvitationAccept, principal: PrincipalDep, request: Request, state: StateDep
) -> InvitationAccepted:
    _limit(state, request)
    if not principal.user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Confirm your email address first, then open the invitation link again.",
        )
    result = await asyncio.to_thread(
        state.accounts.accept_invitation, body.token, principal.user.id, principal.user.email
    )
    if result.status == "wrong_email":
        raise HTTPException(
            status_code=403,
            detail="This invitation was sent to a different email address. Sign in with that address.",
        )
    if result.status != "ok" or result.organization_id is None:
        raise HTTPException(status_code=404, detail=NO_LONGER_VALID)
    await asyncio.to_thread(
        state.audit.record,
        "org.invitation.accepted",
        organization_id=result.organization_id,
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=principal.user.id,
        request_id=request_id(request),
    )
    return InvitationAccepted(organization_id=result.organization_id)
