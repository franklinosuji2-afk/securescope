"""Sign in with Google or GitHub (OAuth 2.0 authorization code flow with PKCE).

What keeps it safe:
* a random `state` is stored with the browser's own random cookie value and the PKCE verifier; the callback
  needs all of them, uses them once and only within ten minutes (no login CSRF, no replay);
* the code is exchanged server to server and the profile is read from the provider over TLS with that token,
  never taken from the browser;
* a sign-in is linked to an existing password account only when the provider says the email is verified;
* if that existing account never confirmed its email, its password is removed and its sessions ended first,
  so someone who registered another person's address in advance cannot get into the real owner's account.

Errors never carry the code, the token or the provider's message back to the browser: only a short reason.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.logging import log_event
from app.repositories.accounts import AccountRepository, DuplicateEmailError, UserRecord
from app.security.tokens import new_token
from app.services.auth import NewSession

logger = logging.getLogger("securescope.oauth")

Provider = Literal["google", "github"]
PROVIDERS: tuple[Provider, ...] = ("google", "github")
STATE_TTL = timedelta(minutes=10)
ERROR_CODES = {"failed", "email_unverified", "disabled", "cancelled", "unavailable"}


class OAuthError(Exception):
    """`code` is one of ERROR_CODES and is safe to show to the user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in ERROR_CODES else "failed"


@dataclass(frozen=True)
class Profile:
    subject: str
    email: str | None
    email_verified: bool


@dataclass(frozen=True)
class SignInResult:
    session: NewSession
    created: bool
    linked: bool


@dataclass(frozen=True)
class StartedSignIn:
    url: str
    browser_token: str


_SPECS: dict[str, dict[str, str]] = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "exchange_url": "https://oauth2.googleapis.com/token",
        "scope": "openid email",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "exchange_url": "https://github.com/login/oauth/access_token",
        "scope": "user:email",
    },
}
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
GITHUB_USER = "https://api.github.com/user"
GITHUB_EMAILS = "https://api.github.com/user/emails"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OAuthService:
    def __init__(
        self,
        accounts: AccountRepository,
        settings: Settings,
        start_session: Callable[[UserRecord], NewSession],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.accounts = accounts
        self.settings = settings
        self._start_session = start_session
        self._client = httpx.Client(timeout=10.0, transport=transport, trust_env=False)
        for name in PROVIDERS:
            has_id = bool(getattr(settings, f"oauth_{name}_client_id", None))
            secret = getattr(settings, f"oauth_{name}_client_secret", None)
            has_secret = secret is not None and bool(secret.get_secret_value())
            if has_id != has_secret:
                # Stays off rather than stopping the API: a typo in the host's settings must not take the site down.
                log_event(logger, "oauth provider is only half configured, so it is switched off", provider=name)

    # --- configuration ----------------------------------------------------------------

    def _credentials(self, provider: str) -> tuple[str, str] | None:
        client_id = getattr(self.settings, f"oauth_{provider}_client_id", None)
        secret = getattr(self.settings, f"oauth_{provider}_client_secret", None)
        if not client_id or secret is None or not secret.get_secret_value():
            return None
        return str(client_id), str(secret.get_secret_value())

    def enabled(self) -> list[str]:
        return [p for p in PROVIDERS if self._credentials(p) is not None]

    def redirect_uri(self, provider: str) -> str:
        return f"{self.settings.public_base_url.rstrip('/')}/api/v1/auth/oauth/{provider}/callback"

    # --- step 1: send the browser to the provider -------------------------------------

    def start(self, provider: str) -> StartedSignIn:
        credentials = self._credentials(provider)
        if credentials is None:
            raise OAuthError("unavailable")
        state, browser, verifier = new_token(), new_token(), new_token()
        self.accounts.create_oauth_state(state, browser, provider, verifier, STATE_TTL)
        spec = _SPECS[provider]
        query = {
            "client_id": credentials[0],
            "redirect_uri": self.redirect_uri(provider),
            "response_type": "code",
            "scope": spec["scope"],
            "state": state,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        }
        if provider == "google":
            query["prompt"] = "select_account"
        return StartedSignIn(f"{spec['authorize_url']}?{urlencode(query)}", browser)

    # --- step 2: the provider sent the browser back -----------------------------------

    def complete(self, provider: str, code: str, state: str, browser: str | None) -> SignInResult:
        credentials = self._credentials(provider)
        if credentials is None:
            raise OAuthError("unavailable")
        verifier = self.accounts.consume_oauth_state(state, browser or "", provider) if browser else None
        if verifier is None:
            raise OAuthError("failed")
        try:
            profile = self._fetch_profile(provider, code, verifier, credentials)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            log_event(logger, "oauth exchange failed", provider=provider, error=type(exc).__name__)
            raise OAuthError("failed") from exc
        try:
            return self._resolve(provider, profile)
        except (IntegrityError, DuplicateEmailError) as exc:
            # Two sign-ins for the same person raced each other; the later one simply fails and can be retried.
            raise OAuthError("failed") from exc

    def _fetch_profile(
        self, provider: str, code: str, verifier: str, credentials: tuple[str, str]
    ) -> Profile:
        response = self._client.post(
            _SPECS[provider]["exchange_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri(provider),
                "client_id": credentials[0],
                "client_secret": credentials[1],
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("no access token")
        auth = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if provider == "google":
            info = self._client.get(GOOGLE_USERINFO, headers=auth)
            info.raise_for_status()
            data = info.json()
            email = data.get("email")
            return Profile(
                subject=str(data["sub"]),
                email=email.lower() if isinstance(email, str) else None,
                email_verified=data.get("email_verified") is True,
            )
        user = self._client.get(GITHUB_USER, headers=auth)
        user.raise_for_status()
        subject = str(user.json()["id"])
        emails = self._client.get(GITHUB_EMAILS, headers=auth)
        emails.raise_for_status()
        chosen = next(
            (
                e["email"].lower()
                for e in emails.json()
                if e.get("primary") is True and e.get("verified") is True and isinstance(e.get("email"), str)
            ),
            None,
        )
        return Profile(subject=subject, email=chosen, email_verified=chosen is not None)

    # --- step 3: decide which account this is -----------------------------------------

    def _resolve(self, provider: str, profile: Profile) -> SignInResult:
        start = self._start_session
        known_id = self.accounts.find_identity_user_id(provider, profile.subject)
        if known_id is not None:
            user = self.accounts.get_user(known_id)
            if user is None or not user.active:
                raise OAuthError("disabled")
            return SignInResult(start(user), created=False, linked=False)
        if not profile.email or not profile.email_verified:
            raise OAuthError("email_unverified")
        existing = self.accounts.get_user_by_email(profile.email)
        if existing is not None:
            return self._link(provider, profile, existing)
        user, _ = self.accounts.create_oauth_user_with_org(
            profile.email, f"{profile.email.split('@')[0]}'s workspace", provider, profile.subject
        )
        return SignInResult(start(user), created=True, linked=False)

    def _link(self, provider: str, profile: Profile, existing: UserRecord) -> SignInResult:
        if not existing.active:
            raise OAuthError("disabled")
        if not profile.email:
            raise OAuthError("email_unverified")
        if not existing.email_verified:
            self.accounts.take_over_unconfirmed_account(existing.id)
        self.accounts.link_identity(existing.id, provider, profile.subject, profile.email)
        user = self.accounts.get_user(existing.id) or existing
        return SignInResult(self._start_session(user), created=False, linked=True)
