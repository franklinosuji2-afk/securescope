"""The signed-in person's own account: change password, delete account."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import PrincipalDep, StateDep, request_id
from app.repositories.accounts import UNUSABLE_PASSWORD
from app.schemas.auth import AccountDelete, PasswordChange
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/account", tags=["account"])


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
        raise HTTPException(status_code=400, detail="Choose a new password that is different from the old one.")
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
        raise HTTPException(status_code=400, detail="Type DELETE to confirm that you want to delete your account.")
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
