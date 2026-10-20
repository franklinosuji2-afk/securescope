from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    PrincipalDep,
    StateDep,
    client_key,
    is_admin,
    request_id,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    OrganizationOut,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth import EmailTakenError, NewSession

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password."


def _user_out(session: NewSession, state: StateDep) -> UserOut:
    return UserOut(
        id=session.user.id,
        email=session.user.email,
        email_verified=session.user.email_verified,
        is_admin=is_admin(session.user, state.settings),
        organizations=[
            OrganizationOut(id=m.organization_id, name=m.name, slug=m.slug, role=m.role)
            for m in session.memberships
        ],
    )


def _set_cookies(response: Response, session: NewSession, state: StateDep) -> None:
    max_age = state.settings.session_ttl_hours * 3600
    secure = state.settings.cookie_secure
    response.set_cookie(
        SESSION_COOKIE, session.token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )
    # Readable by the SPA so it can echo the value in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, request: Request, response: Response, state: StateDep) -> UserOut:
    ip = client_key(request, state)
    if not state.register_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Too many sign-ups from your address. Try again later.")
    state.register_limiter.record(ip)
    try:
        session = await asyncio.to_thread(
            state.auth.register, body.email.lower(), body.password, body.organization_name
        )
    except EmailTakenError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    await asyncio.to_thread(
        state.audit.record,
        "user.registered",
        organization_id=session.memberships[0].organization_id,
        actor_user_id=session.user.id,
        resource_type="user",
        resource_id=session.user.id,
        request_id=request_id(request),
    )
    _set_cookies(response, session, state)
    return _user_out(session, state)


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, request: Request, response: Response, state: StateDep) -> UserOut:
    ip = client_key(request, state)
    email = body.email.lower()
    if not state.login_ip_limiter.check(ip) or not state.login_email_limiter.check(email[:320]):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in a few minutes.")
    session = await asyncio.to_thread(state.auth.login, email, body.password)
    if session is None:
        state.login_ip_limiter.record(ip)
        state.login_email_limiter.record(email[:320])
        await asyncio.to_thread(state.audit.record, "auth.login.failed", request_id=request_id(request))
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    await asyncio.to_thread(
        state.audit.record,
        "auth.login.success",
        organization_id=session.memberships[0].organization_id if session.memberships else None,
        actor_user_id=session.user.id,
        request_id=request_id(request),
    )
    _set_cookies(response, session, state)
    return _user_out(session, state)


@router.post("/logout", status_code=204)
async def logout(principal: PrincipalDep, request: Request, state: StateDep) -> Response:
    await asyncio.to_thread(state.auth.logout, principal.session.id)
    await asyncio.to_thread(
        state.audit.record, "auth.logout", actor_user_id=principal.user.id, request_id=request_id(request)
    )
    response = Response(status_code=204)
    _clear_cookies(response)
    return response


@router.post("/refresh", response_model=UserOut)
async def refresh(principal: PrincipalDep, request: Request, response: Response, state: StateDep) -> UserOut:
    session = await asyncio.to_thread(state.auth.refresh, principal.session.id, principal.user)
    await asyncio.to_thread(
        state.audit.record,
        "auth.session.refreshed",
        actor_user_id=principal.user.id,
        request_id=request_id(request),
    )
    _set_cookies(response, session, state)
    return _user_out(session, state)


@router.get("/me", response_model=UserOut)
async def me(principal: PrincipalDep, state: StateDep) -> UserOut:
    memberships = await asyncio.to_thread(state.accounts.memberships_for_user, principal.user.id)
    return UserOut(
        id=principal.user.id,
        email=principal.user.email,
        email_verified=principal.user.email_verified,
        is_admin=is_admin(principal.user, state.settings),
        organizations=[
            OrganizationOut(id=m.organization_id, name=m.name, slug=m.slug, role=m.role) for m in memberships
        ],
    )


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordRequest, request: Request, state: StateDep) -> dict[str, str]:
    ip = client_key(request, state)
    if not state.reset_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")
    state.reset_limiter.record(ip)
    user_id = await asyncio.to_thread(state.auth.request_password_reset, body.email.lower())
    if user_id:
        await asyncio.to_thread(
            state.audit.record,
            "auth.password_reset.requested",
            actor_user_id=user_id,
            request_id=request_id(request),
        )
    # Identical response whether or not the account exists.
    return {"detail": "If an account exists for that address, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, request: Request, state: StateDep) -> dict[str, str]:
    user_id = await asyncio.to_thread(state.auth.reset_password, body.token, body.password)
    if user_id is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    await asyncio.to_thread(
        state.audit.record,
        "auth.password_reset.completed",
        actor_user_id=user_id,
        request_id=request_id(request),
    )
    return {"detail": "Password updated. Sign in with your new password."}


@router.post("/resend-verification", status_code=202)
async def resend_verification(principal: PrincipalDep, request: Request, state: StateDep) -> dict[str, str]:
    """Sends a fresh confirmation link to the signed-in account (at most 3 per hour)."""
    if principal.user.email_verified:
        return {"detail": "Your email address is already confirmed."}
    key = principal.user.id
    if not state.resend_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many requests. Try again in an hour.")
    state.resend_limiter.record(key)
    await asyncio.to_thread(state.auth.resend_verification, principal.user)
    await asyncio.to_thread(
        state.audit.record,
        "auth.verification_resent",
        actor_user_id=principal.user.id,
        request_id=request_id(request),
    )
    return {"detail": "Confirmation email sent."}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, request: Request, state: StateDep) -> dict[str, str]:
    user_id = await asyncio.to_thread(state.auth.verify_email, body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
    await asyncio.to_thread(
        state.audit.record, "auth.email_verified", actor_user_id=user_id, request_id=request_id(request)
    )
    return {"detail": "Email verified."}
