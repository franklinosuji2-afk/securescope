"""Shared application state and request dependencies (authentication, CSRF, tenancy, RBAC)."""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Request

from app.core.config import Settings
from app.database.session import make_engine
from app.middleware.ratelimit import SlidingWindowLimiter
from app.repositories.accounts import AccountRepository, AuditRepository, SessionRecord, UserRecord
from app.repositories.analytics import AnalyticsRepository
from app.repositories.scans import ScanRepository
from app.repositories.targets import TargetRepository
from app.security.ownership import TxtLookup, system_txt_lookup
from app.security.permissions import Permission, Role, can
from app.security.tokens import constant_time_equal
from app.services.auth import AuthService
from app.services.mailer import Mailer, build_mailer

SESSION_COOKIE = "ss_session"
CSRF_COOKIE = "ss_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
FIFTEEN_MIN = 900.0


class AppState:
    def __init__(self, settings: Settings, mailer: Mailer | None = None) -> None:
        self.settings = settings
        self.engine = make_engine(settings.database_url)
        self.repo = ScanRepository(self.engine)
        self.targets = TargetRepository(self.engine, settings.target_verification_valid_days)
        self.accounts = AccountRepository(self.engine)
        self.analytics = AnalyticsRepository(self.engine)
        salt = (
            settings.analytics_salt.get_secret_value() if settings.analytics_salt else secrets.token_hex(32)
        )
        self.analytics_salt = salt
        self.analytics_limiter = SlidingWindowLimiter(settings.analytics_events_per_client_per_hour)
        self.audit = AuditRepository(self.engine)
        self.auth = AuthService(self.accounts, settings, mailer or build_mailer(settings))
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_scans)
        self.client_limiter = SlidingWindowLimiter(settings.scans_per_client_per_hour)
        self.target_limiter = SlidingWindowLimiter(settings.scans_per_target_per_hour)
        self.login_ip_limiter = SlidingWindowLimiter(settings.login_attempts_per_ip_per_15min, FIFTEEN_MIN)
        self.login_email_limiter = SlidingWindowLimiter(
            settings.login_attempts_per_email_per_15min, FIFTEEN_MIN
        )
        self.register_limiter = SlidingWindowLimiter(settings.registrations_per_ip_per_hour)
        self.reset_limiter = SlidingWindowLimiter(settings.password_reset_requests_per_ip_per_hour)
        self.resend_limiter = SlidingWindowLimiter(3)
        self.verify_limiter = SlidingWindowLimiter(settings.target_verifications_per_target_per_hour)
        # Seams so tests never touch real DNS or the network; production keeps the defaults.
        self.txt_lookup: TxtLookup = system_txt_lookup
        self.verification_transport: httpx.AsyncBaseTransport | None = None
        self.tasks: set[asyncio.Task[None]] = set()
        # Running scan tasks by scan id, so a scan can be cancelled. One process serves all requests.
        self.scan_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def pending(self) -> int:
        return len(self.tasks)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.s
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_key(request: Request, state: AppState) -> str:
    """The address rate limits and login throttling are keyed on.

    Behind the front proxy only an address that arrives with the correct shared secret is believed.
    Anything else falls back to the connection's own peer, which a client cannot choose.
    """
    settings = state.settings
    if settings.trusted_proxy_secret is not None:
        supplied = request.headers.get("x-proxy-secret", "")
        if constant_time_equal(supplied, settings.trusted_proxy_secret.get_secret_value()):
            forwarded = _valid_ip(request.headers.get(settings.client_ip_header, ""))
            if forwarded:
                return forwarded
    if settings.trust_proxy_headers:
        forwarded = _valid_ip(request.headers.get("x-forwarded-for", "").split(",")[0])
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class Principal:
    user: UserRecord
    session: SessionRecord


async def current_principal(request: Request, state: StateDep) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session = await asyncio.to_thread(state.accounts.get_session, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    user = await asyncio.to_thread(state.accounts.get_user, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not constant_time_equal(supplied, session.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    return Principal(user, session)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def is_admin(user: UserRecord, settings: Settings) -> bool:
    """The operator account: the configured admin email, and only once that address is confirmed."""
    configured = (settings.admin_email or "").strip().lower()
    return bool(configured) and user.email.lower() == configured and user.email_verified


async def require_admin(principal: PrincipalDep, state: StateDep) -> Principal:
    if not is_admin(principal.user, state.settings):
        # Same answer as an unknown page, so the dashboards are not advertised to other accounts.
        raise HTTPException(status_code=404, detail="Not found.")
    return principal


AdminDep = Annotated[Principal, Depends(require_admin)]


@dataclass(frozen=True)
class OrgContext:
    principal: Principal
    organization_id: str
    role: Role


async def organization_context(
    principal: PrincipalDep,
    state: StateDep,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> OrgContext:
    """Resolves the active organization. The id comes from the client but is only accepted if the
    authenticated user is a member; it is never trusted on its own."""
    memberships = await asyncio.to_thread(state.accounts.memberships_for_user, principal.user.id)
    if not memberships:
        raise HTTPException(status_code=403, detail="You do not belong to any organization.")
    if x_organization_id is None:
        chosen = memberships[0]
    else:
        match = [m for m in memberships if m.organization_id == x_organization_id]
        if not match:
            raise HTTPException(status_code=403, detail="You are not a member of that organization.")
        chosen = match[0]
    return OrgContext(principal, chosen.organization_id, chosen.role)


OrgDep = Annotated[OrgContext, Depends(organization_context)]


def require(permission: Permission) -> Callable[[OrgContext], Awaitable[OrgContext]]:
    async def checker(ctx: OrgDep) -> OrgContext:
        if not can(ctx.role, permission):
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return ctx

    return checker
