from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import OrgContext, StateDep, request_id, require
from app.repositories.targets import CHALLENGE_TTL, DuplicateTargetError
from app.schemas.target import TargetCreate, TargetList, TargetOut, TargetVerify
from app.security.ownership import (
    OwnershipCheckError,
    verify_dns_txt,
    verify_http_file,
)
from app.security.permissions import Permission
from app.security.target import TargetError, normalize_hostname

router = APIRouter(prefix="/targets", tags=["targets"])

CanRead = Annotated[OrgContext, Depends(require(Permission.TARGET_READ))]
CanManage = Annotated[OrgContext, Depends(require(Permission.TARGET_MANAGE))]


async def _audit(state: StateDep, request: Request, ctx: OrgContext, event: str, target_id: str) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="target",
        resource_id=target_id,
        request_id=request_id(request),
    )


def _valid_id(target_id: str) -> None:
    if not target_id.isalnum() or len(target_id) > 64:
        raise HTTPException(status_code=404, detail="Target not found.")


@router.get("", response_model=TargetList)
async def list_targets(state: StateDep, ctx: CanRead) -> TargetList:
    return TargetList(items=await asyncio.to_thread(state.targets.list, ctx.organization_id))


@router.post("", response_model=TargetOut, status_code=201)
async def create_target(body: TargetCreate, request: Request, state: StateDep, ctx: CanManage) -> TargetOut:
    try:
        hostname = normalize_hostname(body.hostname, state.settings)
    except TargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        target = await asyncio.to_thread(
            state.targets.create, ctx.organization_id, hostname, ctx.principal.user.id
        )
    except DuplicateTargetError as exc:
        raise HTTPException(status_code=409, detail="This host name is already registered.") from exc
    await _audit(state, request, ctx, "target.created", target.id)
    return target


@router.get("/{target_id}", response_model=TargetOut)
async def get_target(target_id: str, state: StateDep, ctx: CanRead) -> TargetOut:
    _valid_id(target_id)
    target = await asyncio.to_thread(state.targets.get, target_id, ctx.organization_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    return target


@router.delete("/{target_id}", status_code=204)
async def delete_target(target_id: str, request: Request, state: StateDep, ctx: CanManage) -> Response:
    _valid_id(target_id)
    if not await asyncio.to_thread(state.targets.delete, target_id, ctx.organization_id):
        raise HTTPException(status_code=404, detail="Target not found.")
    await _audit(state, request, ctx, "target.deleted", target_id)
    return Response(status_code=204)


@router.post("/{target_id}/challenge", response_model=TargetOut)
async def regenerate_challenge(
    target_id: str, request: Request, state: StateDep, ctx: CanManage
) -> TargetOut:
    _valid_id(target_id)
    target = await asyncio.to_thread(state.targets.regenerate_challenge, target_id, ctx.organization_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    await _audit(state, request, ctx, "target.challenge_regenerated", target.id)
    return target


@router.post("/{target_id}/verify", response_model=TargetOut)
async def verify_target(
    target_id: str, body: TargetVerify, request: Request, state: StateDep, ctx: CanManage
) -> TargetOut:
    _valid_id(target_id)
    target = await asyncio.to_thread(state.targets.get, target_id, ctx.organization_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    if target.status == "verified":
        return target
    reverifying = target.status == "reverify"
    if reverifying:
        # A lapsed proof needs a challenge issued after it lapsed, so an old token left on a domain that
        # has since changed hands cannot renew the authorisation.
        lapsed_at = target.verification_expires_at
        issued_at = target.challenge_expires_at - CHALLENGE_TTL
        if lapsed_at is not None and issued_at < lapsed_at:
            raise HTTPException(
                status_code=409,
                detail="The ownership proof has expired. Press New challenge, publish the new value, then verify.",
            )
        if target.challenge_expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=409, detail="The challenge has expired. Generate a new one and publish it."
            )
    if target.status == "expired":
        raise HTTPException(
            status_code=409, detail="The challenge has expired. Generate a new one and publish it."
        )
    key = f"{ctx.organization_id}:{target.id}"
    if not state.verify_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many verification attempts. Try again later.")
    state.verify_limiter.record(key)

    try:
        if body.method == "dns_txt":
            error = await verify_dns_txt(target.hostname, target.challenge_token, state.txt_lookup)
        else:
            error = await verify_http_file(
                target.hostname, target.challenge_token, state.settings, state.verification_transport
            )
    except OwnershipCheckError as exc:
        error = str(exc)
    updated = await asyncio.to_thread(
        state.targets.record_check,
        target.id,
        ctx.organization_id,
        method=body.method,
        error=error,
    )
    if updated is None:  # deleted while the check ran
        raise HTTPException(status_code=404, detail="Target not found.")
    await _audit(
        state,
        request,
        ctx,
        ("target.reverified" if reverifying else "target.verified")
        if error is None
        else "target.verification_failed",
        target.id,
    )
    return updated
