from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import PrincipalDep, StateDep, request_id
from app.repositories.accounts import LastOwnerError
from app.schemas.auth import (
    MemberAdd,
    MemberOut,
    MemberUpdate,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationOut,
)
from app.security.permissions import Permission, Role, can, may_assign

router = APIRouter(prefix="/organizations", tags=["organizations"])

NOT_FOUND = HTTPException(status_code=404, detail="Organization not found.")


async def _membership(state: StateDep, principal: PrincipalDep, organization_id: str):  # type: ignore[no-untyped-def]
    """Non-members get 404, so organization ids cannot be probed."""
    membership = await asyncio.to_thread(state.accounts.membership, organization_id, principal.user.id)
    if membership is None:
        raise NOT_FOUND
    return membership


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Your role does not allow this action.")


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    body: OrganizationCreate, principal: PrincipalDep, request: Request, state: StateDep
) -> OrganizationOut:
    membership = await asyncio.to_thread(state.accounts.create_org, body.name.strip(), principal.user.id)
    await asyncio.to_thread(
        state.audit.record,
        "org.created",
        organization_id=membership.organization_id,
        actor_user_id=principal.user.id,
        resource_type="organization",
        resource_id=membership.organization_id,
        request_id=request_id(request),
    )
    return OrganizationOut(
        id=membership.organization_id, name=membership.name, slug=membership.slug, role=membership.role
    )


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(principal: PrincipalDep, state: StateDep) -> list[OrganizationOut]:
    items = await asyncio.to_thread(state.accounts.memberships_for_user, principal.user.id)
    return [OrganizationOut(id=m.organization_id, name=m.name, slug=m.slug, role=m.role) for m in items]


@router.get("/{organization_id}", response_model=OrganizationDetail)
async def get_organization(
    organization_id: str, principal: PrincipalDep, state: StateDep
) -> OrganizationDetail:
    membership = await _membership(state, principal, organization_id)
    members = await asyncio.to_thread(state.accounts.list_members, organization_id)
    return OrganizationDetail(
        id=membership.organization_id,
        name=membership.name,
        slug=membership.slug,
        role=membership.role,
        members=[
            MemberOut(user_id=m.user_id, email=m.email, role=m.role, joined_at=m.joined_at) for m in members
        ],
    )


@router.post("/{organization_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    organization_id: str, body: MemberAdd, principal: PrincipalDep, request: Request, state: StateDep
) -> MemberOut:
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS) or not may_assign(me.role, body.role):
        raise _forbidden()
    target = await asyncio.to_thread(state.accounts.get_user_by_email, body.email.lower())
    if target is None:
        raise HTTPException(status_code=404, detail="No registered user has that email address.")
    added = await asyncio.to_thread(state.accounts.add_member, organization_id, target.id, body.role)
    if not added:
        raise HTTPException(status_code=409, detail="That user is already a member.")
    await asyncio.to_thread(
        state.audit.record,
        "org.member.added",
        organization_id=organization_id,
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=target.id,
        request_id=request_id(request),
    )
    members = await asyncio.to_thread(state.accounts.list_members, organization_id)
    record = next(m for m in members if m.user_id == target.id)
    return MemberOut(user_id=record.user_id, email=record.email, role=record.role, joined_at=record.joined_at)


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberOut)
async def update_member(
    organization_id: str,
    user_id: str,
    body: MemberUpdate,
    principal: PrincipalDep,
    request: Request,
    state: StateDep,
) -> MemberOut:
    me = await _membership(state, principal, organization_id)
    members = await asyncio.to_thread(state.accounts.list_members, organization_id)
    current = next((m for m in members if m.user_id == user_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS) or not may_assign(me.role, body.role, current.role):
        raise _forbidden()
    try:
        await asyncio.to_thread(state.accounts.set_member_role, organization_id, user_id, body.role)
    except LastOwnerError as exc:
        raise HTTPException(status_code=409, detail="An organization must keep at least one owner.") from exc
    await asyncio.to_thread(
        state.audit.record,
        "org.member.role_changed",
        organization_id=organization_id,
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=user_id,
        request_id=request_id(request),
    )
    return MemberOut(user_id=user_id, email=current.email, role=body.role, joined_at=current.joined_at)


@router.delete("/{organization_id}/members/{user_id}", status_code=204)
async def remove_member(
    organization_id: str, user_id: str, principal: PrincipalDep, request: Request, state: StateDep
) -> Response:
    me = await _membership(state, principal, organization_id)
    members = await asyncio.to_thread(state.accounts.list_members, organization_id)
    current = next((m for m in members if m.user_id == user_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    leaving = user_id == principal.user.id
    if not leaving and (
        not can(me.role, Permission.ORG_MANAGE_MEMBERS) or not may_assign(me.role, Role.VIEWER, current.role)
    ):
        raise _forbidden()
    try:
        await asyncio.to_thread(state.accounts.remove_member, organization_id, user_id)
    except LastOwnerError as exc:
        raise HTTPException(status_code=409, detail="An organization must keep at least one owner.") from exc
    await asyncio.to_thread(
        state.audit.record,
        "org.member.removed",
        organization_id=organization_id,
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=user_id,
        request_id=request_id(request),
    )
    return Response(status_code=204)
