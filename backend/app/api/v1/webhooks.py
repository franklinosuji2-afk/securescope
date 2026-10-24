"""Webhook alerts: endpoints a workspace has chosen, with a signing secret shown once."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import OrgContext, StateDep, request_id, require
from app.repositories.webhooks import MAX_PER_ORGANIZATION
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryOut,
    WebhookList,
    WebhookOut,
    WebhookTestResult,
    WebhookUpdate,
)
from app.security.permissions import Permission
from app.security.target import TargetError

router = APIRouter(prefix="/webhooks", tags=["webhook alerts"])

CanRead = Annotated[OrgContext, Depends(require(Permission.SCAN_READ))]
CanManage = Annotated[OrgContext, Depends(require(Permission.TARGET_MANAGE))]
NOT_INCLUDED = (
    "Webhook alerts are part of the Professional and Agency plans. Your plan does not include them."
)
NOT_CONFIGURED = "Webhook alerts are not switched on for this server."
NOT_FOUND = "Webhook not found."


def _check_id(webhook_id: str) -> None:
    if not webhook_id.isalnum() or len(webhook_id) > 64:
        raise HTTPException(status_code=404, detail=NOT_FOUND)


async def _audit(state: StateDep, request: Request, ctx: OrgContext, event: str, webhook_id: str) -> None:
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.principal.user.id,
        resource_type="webhook",
        resource_id=webhook_id,
        request_id=request_id(request),
    )


@router.get("", response_model=WebhookList)
async def list_webhooks(state: StateDep, ctx: CanRead) -> WebhookList:
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    items = await asyncio.to_thread(state.webhook_repo.list_for_organization, ctx.organization_id)
    return WebhookList(
        available=plan.scheduled_scans,
        configured=state.webhooks.configured,
        limit=MAX_PER_ORGANIZATION,
        items=items,
    )


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(webhook_id: str, state: StateDep, ctx: CanRead) -> list[WebhookDeliveryOut]:
    """The last deliveries to one address: when, which event and the outcome. No message content."""
    _check_id(webhook_id)
    items = await asyncio.to_thread(state.webhook_repo.deliveries, ctx.organization_id, webhook_id)
    if items is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return items


@router.post("", response_model=WebhookCreated, status_code=201)
async def create_webhook(
    body: WebhookCreate, request: Request, state: StateDep, ctx: CanManage
) -> WebhookCreated:
    if not state.webhooks.configured:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    plan = await state.entitlements.plan_for_async(ctx.organization_id)
    if not plan.scheduled_scans:
        raise HTTPException(status_code=403, detail=NOT_INCLUDED)
    try:
        url = await state.webhooks.validate_address(body.url, body.kind)
    except TargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    created = await asyncio.to_thread(
        state.webhook_repo.create, ctx.organization_id, url, ctx.principal.user.id, body.kind
    )
    if created is None:
        raise HTTPException(
            status_code=409, detail=f"A workspace can have {MAX_PER_ORGANIZATION} webhook addresses at most."
        )
    endpoint, out = created
    await _audit(state, request, ctx, "webhook.created", endpoint.id)
    secret = state.webhooks.secret_for(endpoint) if body.kind == "webhook" else None
    return WebhookCreated(**out.model_dump(), signing_secret=secret)


@router.post("/{webhook_id}/test", response_model=WebhookTestResult)
async def test_webhook(webhook_id: str, state: StateDep, ctx: CanManage) -> WebhookTestResult:
    _check_id(webhook_id)
    if not state.webhooks.configured:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    endpoint = await asyncio.to_thread(state.webhook_repo.get, ctx.organization_id, webhook_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    key = f"{ctx.organization_id}"
    if not state.webhook_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many test messages. Try again later.")
    state.webhook_limiter.record(key)
    ok, status = await state.webhooks.send_test(endpoint)
    return WebhookTestResult(ok=ok, status=status)


@router.post("/{webhook_id}/rotate", response_model=WebhookCreated)
async def rotate_webhook(
    webhook_id: str, request: Request, state: StateDep, ctx: CanManage
) -> WebhookCreated:
    _check_id(webhook_id)
    if not state.webhooks.configured:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
    existing = await asyncio.to_thread(state.webhook_repo.get, ctx.organization_id, webhook_id)
    if existing is not None and existing.kind == "slack":
        raise HTTPException(status_code=400, detail="A Slack address has no signing secret to renew.")
    endpoint = await asyncio.to_thread(state.webhook_repo.rotate, ctx.organization_id, webhook_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    items = await asyncio.to_thread(state.webhook_repo.list_for_organization, ctx.organization_id)
    out = next(i for i in items if i.id == webhook_id)
    await _audit(state, request, ctx, "webhook.secret_renewed", webhook_id)
    return WebhookCreated(**out.model_dump(), signing_secret=state.webhooks.secret_for(endpoint))


@router.put("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: str, body: WebhookUpdate, request: Request, state: StateDep, ctx: CanManage
) -> WebhookOut:
    _check_id(webhook_id)
    out = await asyncio.to_thread(
        state.webhook_repo.set_enabled, ctx.organization_id, webhook_id, body.enabled
    )
    if out is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    await _audit(state, request, ctx, "webhook.updated", webhook_id)
    return out


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, request: Request, state: StateDep, ctx: CanManage) -> None:
    _check_id(webhook_id)
    removed = await asyncio.to_thread(state.webhook_repo.delete, ctx.organization_id, webhook_id)
    if not removed:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    await _audit(state, request, ctx, "webhook.deleted", webhook_id)
