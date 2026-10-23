"""Integrations for people: API tokens for CI and score badges. The public badge image is served here too."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import OrgContext, StateDep, client_key, request_id, require
from app.repositories.integrations import MAX_TOKENS_PER_ORGANIZATION, badge_url
from app.schemas.integration import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenList,
    BadgeList,
    BadgeOut,
    BadgeUpdate,
)
from app.security.permissions import Permission
from app.services.badge import render_badge

router = APIRouter(tags=["integrations"])
badge_router = APIRouter(prefix="/badges", tags=["badges"])

CanManageTokens = Annotated[OrgContext, Depends(require(Permission.ORG_MANAGE_MEMBERS))]
CanReadTargets = Annotated[OrgContext, Depends(require(Permission.TARGET_READ))]
CanManageTargets = Annotated[OrgContext, Depends(require(Permission.TARGET_MANAGE))]
NOT_INCLUDED = (
    "API tokens for CI are part of the Professional and Agency plans. Your plan does not include them."
)
BADGE_HEADERS = {
    "Content-Type": "image/svg+xml",
    "Cache-Control": "public, max-age=300",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
}


async def _audit(
    state: StateDep, request: Request, ctx: OrgContext, event: str, resource_type: str, resource_id: str
) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id(request),
    )


def _check_id(value: str) -> None:
    if not value.isalnum() or len(value) > 64:
        raise HTTPException(status_code=404, detail="Not found.")


# --- API tokens ------------------------------------------------------------------------------------------


@router.get("/api-tokens", response_model=ApiTokenList)
async def list_tokens(state: StateDep, ctx: CanManageTokens) -> ApiTokenList:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    items = await asyncio.to_thread(state.integrations.list_tokens, ctx.organization_id)
    return ApiTokenList(available=plan.scheduled_scans, limit=MAX_TOKENS_PER_ORGANIZATION, items=items)


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=201)
async def create_token(
    body: ApiTokenCreate, request: Request, state: StateDep, ctx: CanManageTokens
) -> ApiTokenCreated:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    if not plan.scheduled_scans:
        raise HTTPException(status_code=403, detail=NOT_INCLUDED)
    key = ctx.organization_id
    if not state.token_admin_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many changes. Try again later.")
    state.token_admin_limiter.record(key)
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status_code=400, detail="Give the token a name.")
    created = await asyncio.to_thread(
        state.integrations.create_token, ctx.organization_id, ctx.principal.user.id, name
    )
    if created is None:
        raise HTTPException(
            status_code=409,
            detail=f"A workspace can have {MAX_TOKENS_PER_ORGANIZATION} API tokens at most. Remove one first.",
        )
    out, token = created
    await _audit(state, request, ctx, "api_token.created", "api_token", out.id)
    return ApiTokenCreated(**out.model_dump(), token=token)


@router.delete("/api-tokens/{token_id}", status_code=204)
async def revoke_token(token_id: str, request: Request, state: StateDep, ctx: CanManageTokens) -> None:
    _check_id(token_id)
    removed = await asyncio.to_thread(state.integrations.revoke_token, ctx.organization_id, token_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Token not found.")
    await _audit(state, request, ctx, "api_token.revoked", "api_token", token_id)


# --- badges ----------------------------------------------------------------------------------------------


@router.get("/badges", response_model=BadgeList)
async def list_badges(state: StateDep, ctx: CanReadTargets) -> BadgeList:
    items = await asyncio.to_thread(
        state.integrations.list_badges, ctx.organization_id, state.settings.public_base_url
    )
    return BadgeList(items=items)


@router.put("/badges/{target_id}", response_model=BadgeOut)
async def set_badge(
    target_id: str, body: BadgeUpdate, request: Request, state: StateDep, ctx: CanManageTargets
) -> BadgeOut:
    _check_id(target_id)
    result = await asyncio.to_thread(
        state.integrations.set_badge, ctx.organization_id, target_id, body.enabled, body.renew
    )
    if result is False:
        raise HTTPException(status_code=404, detail="Site not found, or it is not verified yet.")
    await _audit(state, request, ctx, "badge.updated", "target", target_id)
    items = await asyncio.to_thread(
        state.integrations.list_badges, ctx.organization_id, state.settings.public_base_url
    )
    return next(i for i in items if i.target_id == target_id)


@badge_router.get("/{filename}")
async def public_badge(filename: str, request: Request, state: StateDep) -> Response:
    """The image itself. No sign-in: the long random address is the permission, and it shows only the latest
    score and grade of one site the owner chose to show."""
    key = client_key(request, state)
    if not state.badge_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many requests.")
    state.badge_limiter.record(key)
    token = filename[:-4] if filename.endswith(".svg") else ""
    subject = await asyncio.to_thread(state.integrations.badge_subject, token) if token else None
    if subject is None:
        return Response(
            render_badge(None, available=False),
            status_code=404,
            headers={**BADGE_HEADERS, "Cache-Control": "no-store"},
        )
    reading = await asyncio.to_thread(
        state.integrations.latest_reading, subject.organization_id, subject.hostname
    )
    return Response(render_badge(reading), headers=BADGE_HEADERS)


__all__ = ["badge_router", "badge_url", "router"]
