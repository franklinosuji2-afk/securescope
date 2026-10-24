"""The signed-in person's own account: change password, delete account."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import PrincipalDep, StateDep, request_id
from app.repositories.accounts import UNUSABLE_PASSWORD
from app.schemas.auth import AccountDelete, PasswordChange
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/account", tags=["account"])


class AccountOut(BaseModel):
    email: str
    email_verified: bool
    status: str
    created_at: datetime
    has_password: bool


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    current: bool


@router.get("", response_model=AccountOut)
async def account_details(principal: PrincipalDep, state: StateDep) -> AccountOut:
    """The signed-in person's own account facts."""
    details = await asyncio.to_thread(state.accounts.account_details, principal.user.id)
    if details is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return AccountOut(
        email=principal.user.email,
        email_verified=principal.user.email_verified,
        status=details.status.lower(),
        created_at=details.created_at,
        has_password=principal.user.password_hash != UNUSABLE_PASSWORD,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(principal: PrincipalDep, state: StateDep) -> list[SessionOut]:
    """The person's own signed-in devices. Other people's sessions can never be listed."""
    rows = await asyncio.to_thread(state.accounts.list_sessions, principal.user.id)
    return [
        SessionOut(
            id=r.id, created_at=r.created_at, expires_at=r.expires_at, current=r.id == principal.session.id
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str, request: Request, principal: PrincipalDep, state: StateDep
) -> Response:
    """Signs out one other device. To end this device's session, sign out normally."""
    if session_id == principal.session.id:
        raise HTTPException(status_code=400, detail="This is the device you are using. Use Sign out instead.")
    done = await asyncio.to_thread(state.accounts.revoke_user_session, principal.user.id, session_id)
    if not done:
        raise HTTPException(status_code=404, detail="Session not found.")
    await asyncio.to_thread(
        state.audit.record,
        "account.session_revoked",
        actor_user_id=principal.user.id,
        resource_type="session",
        request_id=request_id(request),
    )
    return Response(status_code=204)


@router.post("/sessions/revoke-others", status_code=204)
async def revoke_other_sessions(request: Request, principal: PrincipalDep, state: StateDep) -> Response:
    """Signs out every device except this one."""
    await asyncio.to_thread(state.accounts.revoke_other_sessions, principal.user.id, principal.session.id)
    await asyncio.to_thread(
        state.audit.record,
        "account.other_sessions_revoked",
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=principal.user.id,
        request_id=request_id(request),
    )
    return Response(status_code=204)


@router.get("/export")
async def export_data(request: Request, principal: PrincipalDep, state: StateDep) -> Response:
    """A JSON file with the person's own account data. See `export_personal_data` for what it leaves out."""
    data = await asyncio.to_thread(state.accounts.export_personal_data, principal.user.id)
    await asyncio.to_thread(
        state.audit.record,
        "account.data_exported",
        actor_user_id=principal.user.id,
        resource_type="user",
        resource_id=principal.user.id,
        request_id=request_id(request),
    )
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="securescope-account-data.json"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/password", status_code=204)
async def change_password(
    body: PasswordChange, request: Request, principal: PrincipalDep, state: StateDep
) -> Response:
    """Sets a new password. Every other signed-in device is signed out; this one stays signed in."""
    user = principal.user
    key = user.id
    if not state.password_change_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")
    if user.password_hash == UNUSABLE_PASSWORD:
        raise HTTPException(
            status_code=400,
            detail="This account signs in with Google or GitHub and has no password yet. "
            "Use 'Forgot password' on the sign-in page to set one.",
        )
    valid = await asyncio.to_thread(verify_password, user.password_hash, body.current_password)
    if not valid:
        state.password_change_limiter.record(key)
        raise HTTPException(status_code=400, detail="Your current password is not correct.")
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=400, detail="Choose a new password that is different from the old one."
        )
    new_hash = await asyncio.to_thread(hash_password, body.new_password)
    await asyncio.to_thread(state.accounts.set_password, user.id, new_hash)
    await asyncio.to_thread(state.accounts.revoke_other_sessions, user.id, principal.session.id)
    await asyncio.to_thread(
        state.audit.record,
        "account.password_changed",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        request_id=request_id(request),
    )
    await asyncio.to_thread(
        state.auth.mailer.send,
        user.email,
        "Your SecureScope password was changed",
        "The password for your SecureScope account was just changed. If this was you, there is nothing "
        "to do. If it was not you, reset your password right away and contact support@getsecurescope.com.",
    )
    return Response(status_code=204)


@router.delete("", status_code=204)
async def delete_account(
    body: AccountDelete, request: Request, principal: PrincipalDep, state: StateDep
) -> Response:
    """Permanently deletes the account and everything only this person had: their sites, scans, findings
    and reports. A workspace shared with other people is kept; this person just leaves it."""
    user = principal.user
    if body.confirm != "DELETE":
        raise HTTPException(
            status_code=400, detail="Type DELETE to confirm that you want to delete your account."
        )
    if user.password_hash != UNUSABLE_PASSWORD:
        if not state.password_change_limiter.check(user.id):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")
        valid = await asyncio.to_thread(verify_password, user.password_hash, body.password)
        if not valid:
            state.password_change_limiter.record(user.id)
            raise HTTPException(status_code=400, detail="Your password is not correct.")
    blocking = await asyncio.to_thread(state.accounts.organizations_blocking_deletion, user.id)
    if blocking:
        raise HTTPException(
            status_code=409,
            detail=(
                f"You are the only owner of {', '.join(blocking)}, which other people still use. "
                "Make someone else an owner or remove the other members first."
            ),
        )
    await asyncio.to_thread(state.accounts.delete_account, user.id)
    await asyncio.to_thread(
        state.audit.record,
        "account.deleted",
        resource_type="user",
        resource_id=user.id,
        request_id=request_id(request),
    )
    await asyncio.to_thread(
        state.auth.mailer.send,
        user.email,
        "Your SecureScope account was deleted",
        "Your SecureScope account and its data have been deleted, as you asked. "
        "Nothing more is needed from you.",
    )
    response = Response(status_code=204)
    response.delete_cookie("ss_session", path="/")
    response.delete_cookie("ss_csrf", path="/")
    return response
