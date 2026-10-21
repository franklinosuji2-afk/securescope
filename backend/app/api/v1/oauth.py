"""Sign in with Google or GitHub. See app/services/oauth.py for how the flow is protected."""

from __future__ import annotations

import asyncio
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.api.deps import StateDep, client_key, request_id
from app.api.v1.auth import _set_cookies
from app.services.oauth import OAuthError

router = APIRouter(prefix="/auth", tags=["auth"])

BROWSER_COOKIE = "ss_oauth"
BROWSER_COOKIE_PATH = "/api/v1/auth/oauth"
ProviderName = Literal["google", "github"]


def _home(state: StateDep, fragment: str = "/") -> str:
    return f"{state.settings.public_base_url.rstrip('/')}/#{fragment}"


def _failure(state: StateDep, code: str) -> RedirectResponse:
    response = RedirectResponse(_home(state, f"/login?{urlencode({'oauth_error': code})}"), status_code=302)
    response.delete_cookie(BROWSER_COOKIE, path=BROWSER_COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/providers")
async def providers(state: StateDep) -> dict[str, list[str]]:
    """Which sign-in buttons to show: only providers that are configured."""
    return {"providers": state.oauth.enabled()}


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: ProviderName, request: Request, state: StateDep) -> RedirectResponse:
    if provider not in state.oauth.enabled():
        raise HTTPException(status_code=404, detail="This sign-in method is not available.")
    ip = client_key(request, state)
    if not state.oauth_limiter.check(ip):
        return _failure(state, "failed")
    state.oauth_limiter.record(ip)
    started = await asyncio.to_thread(state.oauth.start, provider)
    response = RedirectResponse(started.url, status_code=302)
    response.set_cookie(
        BROWSER_COOKIE,
        started.browser_token,
        max_age=600,
        httponly=True,
        secure=state.settings.cookie_secure,
        samesite="lax",
        path=BROWSER_COOKIE_PATH,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: ProviderName,
    request: Request,
    state: StateDep,
    code: str | None = Query(default=None, max_length=2048),
    state_value: str | None = Query(default=None, alias="state", max_length=256),
    error: str | None = Query(default=None, max_length=200),
) -> RedirectResponse:
    ip = client_key(request, state)
    if not state.oauth_limiter.check(ip):
        return _failure(state, "failed")
    state.oauth_limiter.record(ip)
    if error:
        # The person declined at the provider, or the provider refused. Nothing else is passed on.
        return _failure(state, "cancelled" if error == "access_denied" else "failed")
    if not code or not state_value:
        return _failure(state, "failed")
    try:
        result = await asyncio.to_thread(
            state.oauth.complete, provider, code, state_value, request.cookies.get(BROWSER_COOKIE)
        )
    except OAuthError as exc:
        await asyncio.to_thread(
            state.audit.record, "auth.oauth.failed", resource_type="oauth", resource_id=provider,
            request_id=request_id(request),
        )
        return _failure(state, exc.code)
    session = result.session
    org_id = session.memberships[0].organization_id if session.memberships else None
    event = "user.registered" if result.created else "auth.oauth.linked" if result.linked else "auth.oauth.login"
    await asyncio.to_thread(
        state.audit.record,
        event,
        organization_id=org_id,
        actor_user_id=session.user.id,
        resource_type="user",
        resource_id=session.user.id,
        request_id=request_id(request),
    )
    response = RedirectResponse(_home(state), status_code=302)
    _set_cookies(response, session, state)
    response.delete_cookie(BROWSER_COOKIE, path=BROWSER_COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return response

