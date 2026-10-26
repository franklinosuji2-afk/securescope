"""CI access: a bearer token starts and reads scans of the workspace's verified sites, for the GitHub Action.

A token does nothing else. It cannot read reports or other data, change settings or manage tokens. It acts as the
person who made it, inside one workspace, so a person who leaves the workspace takes their tokens with them.
Every safety check of a normal scan still applies: ownership, rate limits and the monthly allowance.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import StateDep, client_key
from app.api.v1.scans import Actor, start_scan
from app.schemas.integration import CiFinding, CiScanCreate, CiScanOut
from app.schemas.scan import SEVERITY_ORDER, FindingStatus, ScanDetail, ScanStatus
from app.security.permissions import Permission, can

router = APIRouter(prefix="/ci", tags=["ci"])

NOT_INCLUDED = "CI access is part of the Professional and Agency plans. Your plan does not include it."
MAX_FINDINGS = 100


@dataclass(frozen=True)
class CiActor:
    organization_id: str
    user_id: str
    token_id: str


async def bearer_actor(request: Request, state: StateDep, authorization: str | None, scope: str) -> CiActor:
    """Authenticates a bearer token for one scope. A token of another scope, an unknown, revoked or expired
    token, and a token whose owner has lost access all get the same answer."""
    client = client_key(request, state)
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Send the API token as: Authorization: Bearer <token>.")
    if not state.ci_bad_token_limiter.check(client):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    identity = await asyncio.to_thread(state.integrations.authenticate, token.strip())
    if identity is None or identity.scope != scope:
        state.ci_bad_token_limiter.record(client)
        raise HTTPException(status_code=401, detail="The API token is not valid, or it has been removed.")
    # The token is only as strong as the person behind it is today.
    user = await asyncio.to_thread(state.accounts.get_user, identity.user_id)
    membership = await asyncio.to_thread(
        state.accounts.membership, identity.organization_id, identity.user_id
    )
    if (
        user is None
        or not user.active
        or membership is None
        or not can(membership.role, Permission.SCAN_CREATE)
    ):
        state.ci_bad_token_limiter.record(client)
        raise HTTPException(status_code=401, detail="The API token is not valid, or it has been removed.")
    if not state.ci_limiter.check(identity.token_id):
        raise HTTPException(status_code=429, detail="Too many requests for this token. Try again later.")
    state.ci_limiter.record(identity.token_id)
    return CiActor(identity.organization_id, identity.user_id, identity.token_id)


async def ci_actor(
    request: Request, state: StateDep, authorization: Annotated[str | None, Header()] = None
) -> CiActor:
    return await bearer_actor(request, state, authorization, "web")


CiDep = Annotated[CiActor, Depends(ci_actor)]


def _out(detail: ScanDetail, base_url: str) -> CiScanOut:
    order = {s.value: i for i, s in enumerate(SEVERITY_ORDER)}
    # Findings the team decided about (false positive, accepted risk) must not fail a pipeline.
    open_findings = [f for f in detail.findings if f.status is FindingStatus.OPEN]
    findings = sorted(open_findings, key=lambda f: (order[f.severity.value], f.id))
    counts = {s.value: sum(1 for f in open_findings if f.severity is s) for s in SEVERITY_ORDER}
    return CiScanOut(
        id=detail.id,
        host=detail.host,
        status=detail.status.value,
        score=detail.score,
        grade=detail.grade,
        counts=counts if detail.status is ScanStatus.COMPLETED else detail.counts,
        findings=[
            CiFinding(id=f.id, severity=f.severity.value, title=f.title) for f in findings[:MAX_FINDINGS]
        ],
        error=detail.error,
        link=f"{base_url.rstrip('/')}/#/findings?scan={detail.id}",
    )


@router.post("/scans", response_model=CiScanOut, status_code=202)
async def start_ci_scan(body: CiScanCreate, request: Request, state: StateDep, actor: CiDep) -> CiScanOut:
    plan = await state.entitlements.plan_for_async(actor.organization_id)
    if not plan.scheduled_scans:
        raise HTTPException(status_code=403, detail=NOT_INCLUDED)
    detail = await start_scan(state, request, Actor(actor.organization_id, actor.user_id), body.url.strip())
    return _out(detail, state.settings.public_base_url)


@router.get("/scans/{scan_id}", response_model=CiScanOut)
async def get_ci_scan(scan_id: str, state: StateDep, actor: CiDep) -> CiScanOut:
    if not scan_id.isalnum() or len(scan_id) > 64:
        raise HTTPException(status_code=404, detail="Scan not found.")
    detail = await asyncio.to_thread(state.repo.get_scan, scan_id, actor.organization_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return _out(detail, state.settings.public_base_url)
