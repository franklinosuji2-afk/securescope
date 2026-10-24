from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import PrincipalDep, StateDep, request_id
from app.billing.plans import PLANS
from app.billing.preview import downgrade_effects
from app.repositories.accounts import LastOwnerError
from app.schemas.auth import (
    InvitationCreate,
    InvitationOut,
    MemberAdd,
    MemberOut,
    MemberUpdate,
    OrganizationCreate,
    OrganizationDetail,
    OrganizationOut,
)
from app.schemas.billing import (
    DowngradeEffectOut,
    DowngradePreview,
    PlanLimits,
    PlanOut,
    PlanUsage,
    SubscriptionOut,
)
from app.security.permissions import Permission, Role, can, may_assign
from app.services.invitations import MAX_PENDING_PER_ORGANIZATION

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
    if membership.role is Role.VIEWER:
        # A viewer is typically a client. Clients must not learn who else (other clients, staff) belongs
        # to the workspace, so they get only their own entry.
        members = [m for m in members if m.user_id == principal.user.id]
    return OrganizationDetail(
        id=membership.organization_id,
        name=membership.name,
        slug=membership.slug,
        role=membership.role,
        members=[
            MemberOut(user_id=m.user_id, email=m.email, role=m.role, joined_at=m.joined_at) for m in members
        ],
    )


@router.get("/{organization_id}/plan", response_model=PlanOut)
async def get_plan(organization_id: str, principal: PrincipalDep, state: StateDep) -> PlanOut:
    """The workspace's plan, its limits and what has been used. Owners and admins only: clients do not see billing."""
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS):
        raise _forbidden()
    summary = await asyncio.to_thread(state.entitlements.summary, organization_id)
    plan = summary.plan
    sub = await asyncio.to_thread(state.billing.subscription, organization_id)
    return PlanOut(
        plan_id=plan.id,
        name=plan.name,
        price_eur_month=plan.price_eur_month,
        limits=PlanLimits(
            websites=plan.max_websites,
            scans_per_month=plan.scans_per_month,
            history_days=plan.history_days,
            can_invite=plan.can_invite,
            client_workspace=plan.client_workspace,
            scheduled_scans=plan.scheduled_scans,
        ),
        usage=PlanUsage(
            websites=summary.websites_used,
            scans_this_period=summary.scans_used,
            period_start=summary.period_start,
            period_end=summary.period_end,
        ),
        subscription=SubscriptionOut(
            status=sub.status,
            plan_id=sub.plan_id,
            current_period_end=sub.current_period_end,
            cancel_at_period_end=sub.cancel_at_period_end,
            pending_plan_id=sub.pending_plan_id,
        )
        if sub
        else None,
    )


@router.get("/{organization_id}/plan/downgrade-preview", response_model=DowngradePreview)
async def downgrade_preview(
    organization_id: str, to: str, principal: PrincipalDep, state: StateDep
) -> DowngradePreview:
    """What moving to a lower plan would change, so nobody is surprised. It only counts: nothing is changed or
    deleted. Owners and admins only, like the plan itself."""
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS):
        raise _forbidden()
    target = PLANS.get(to)
    if target is None or target.id == "internal":
        raise HTTPException(status_code=404, detail="Unknown plan.")
    summary = await asyncio.to_thread(state.entitlements.summary, organization_id)
    usage = await asyncio.to_thread(
        state.billing.usage, organization_id, summary.period_start, summary.plan.history_days
    )
    effects = downgrade_effects(summary.plan, target, usage)
    return DowngradePreview(
        current_plan_id=summary.plan.id,
        target_plan_id=target.id,
        target_name=target.name,
        effects=[DowngradeEffectOut(**asdict(e)) for e in effects],
    )


@router.post("/{organization_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    organization_id: str, body: MemberAdd, principal: PrincipalDep, request: Request, state: StateDep
) -> MemberOut:
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS) or not may_assign(me.role, body.role):
        raise _forbidden()
    plan = await state.entitlements.plan_for_async(organization_id)
    if not plan.can_invite:
        raise HTTPException(
            status_code=403,
            detail=f"Adding people is part of the Agency plan. This workspace is on the {plan.name} plan.",
        )
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


def _invitation_out(record) -> InvitationOut:  # type: ignore[no-untyped-def]
    return InvitationOut(
        id=record.id,
        email=record.email,
        role=record.role,
        invited_by_email=record.invited_by_email,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@router.get("/{organization_id}/invitations", response_model=list[InvitationOut])
async def list_invitations(
    organization_id: str, principal: PrincipalDep, state: StateDep
) -> list[InvitationOut]:
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS):
        raise _forbidden()
    items = await asyncio.to_thread(state.accounts.list_pending_invitations, organization_id)
    return [_invitation_out(item) for item in items]


@router.post("/{organization_id}/invitations", response_model=InvitationOut, status_code=201)
async def create_invitation(
    organization_id: str,
    body: InvitationCreate,
    principal: PrincipalDep,
    request: Request,
    state: StateDep,
) -> InvitationOut:
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS) or not may_assign(me.role, body.role):
        raise _forbidden()
    if body.role is Role.OWNER:
        raise HTTPException(
            status_code=400,
            detail="An invitation cannot make someone an owner. Invite them first, then change the role.",
        )
    plan = await state.entitlements.plan_for_async(organization_id)
    if not plan.can_invite:
        raise HTTPException(
            status_code=403,
            detail=f"Inviting people is part of the Agency plan. This workspace is on the {plan.name} plan.",
        )
    if not state.invite_send_limiter.check(principal.user.id):
        raise HTTPException(status_code=429, detail="Too many invitations sent. Try again later.")
    address = body.email.lower()
    members = await asyncio.to_thread(state.accounts.list_members, organization_id)
    if any(m.email.lower() == address for m in members):
        raise HTTPException(status_code=409, detail="That person is already a member.")
    pending = await asyncio.to_thread(state.accounts.list_pending_invitations, organization_id)
    if len(pending) >= MAX_PENDING_PER_ORGANIZATION and not any(p.email == address for p in pending):
        raise HTTPException(status_code=409, detail="Too many pending invitations. Revoke some first.")
    state.invite_send_limiter.record(principal.user.id)
    record = await asyncio.to_thread(
        state.invitations.invite, organization_id, address, body.role, principal.user
    )
    await asyncio.to_thread(
        state.audit.record,
        "org.invitation.created",
        organization_id=organization_id,
        actor_user_id=principal.user.id,
        resource_type="invitation",
        resource_id=record.id,
        request_id=request_id(request),
    )
    return _invitation_out(record)


@router.delete("/{organization_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    principal: PrincipalDep,
    request: Request,
    state: StateDep,
) -> Response:
    me = await _membership(state, principal, organization_id)
    if not can(me.role, Permission.ORG_MANAGE_MEMBERS):
        raise _forbidden()
    revoked = await asyncio.to_thread(state.accounts.revoke_invitation, organization_id, invitation_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    await asyncio.to_thread(
        state.audit.record,
        "org.invitation.revoked",
        organization_id=organization_id,
        actor_user_id=principal.user.id,
        resource_type="invitation",
        resource_id=invitation_id,
        request_id=request_id(request),
    )
    return Response(status_code=204)
