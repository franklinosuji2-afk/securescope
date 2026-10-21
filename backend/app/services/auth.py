"""Account workflows: registration, login, sessions, email verification, password reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.core.config import Settings
from app.repositories.accounts import (
    AccountRepository,
    DuplicateEmailError,
    OrgMembership,
    UserRecord,
)
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import new_token
from app.services.mailer import Mailer

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)


LINK_INTRO = {
    "verify_email": (
        "Welcome to SecureScope.\n\nPlease confirm your email address to start using your dashboard. "
        "The link below works for {hours} hours. If you did not create an account, you can ignore this email."
    ),
    "reset_password": (  # noqa: S105  # nosec B105
        "We received a request to reset your SecureScope password.\n\nOpen the link below to choose a "
        "new one. It works for {hours} hour. If you did not ask for this, you can ignore this email; "
        "your password has not changed."
    ),
}


class EmailTakenError(Exception):
    pass


@dataclass(frozen=True)
class NewSession:
    user: UserRecord
    token: str
    csrf_token: str
    memberships: list[OrgMembership]


class AuthService:
    def __init__(self, accounts: AccountRepository, settings: Settings, mailer: Mailer) -> None:
        self.accounts = accounts
        self.settings = settings
        self.mailer = mailer

    @property
    def _ttl(self) -> timedelta:
        return timedelta(hours=self.settings.session_ttl_hours)

    def _start_session(self, user: UserRecord) -> NewSession:
        token, csrf = new_token(), new_token()
        self.accounts.create_session(user.id, token, csrf, self._ttl)
        return NewSession(user, token, csrf, self.accounts.memberships_for_user(user.id))

    def begin_session(self, user: UserRecord) -> NewSession:
        """Starts a session for an account that has already proven who it is (used by provider sign-in)."""
        return self._start_session(user)

    def _send_link(self, user: UserRecord, kind: str, path: str, subject: str, ttl: timedelta) -> None:
        token = new_token()
        self.accounts.create_account_token(user.id, kind, token, ttl)
        link = f"{self.settings.public_base_url.rstrip('/')}/{path}?token={token}"
        hours = int(ttl.total_seconds() // 3600)
        intro = LINK_INTRO[kind].format(hours=hours)
        self.mailer.send(user.email, subject, f"{intro}\n\n{link}")

    def register(self, email: str, password: str, organization_name: str | None) -> NewSession:
        try:
            user, _ = self.accounts.create_user_with_org(
                email, hash_password(password), organization_name or f"{email.split('@')[0]}'s workspace"
            )
        except DuplicateEmailError as exc:
            raise EmailTakenError from exc
        self._send_link(user, "verify_email", "verify-email", "Confirm your SecureScope email", VERIFY_TTL)
        return self._start_session(user)

    def resend_verification(self, user: UserRecord) -> None:
        self._send_link(user, "verify_email", "verify-email", "Confirm your SecureScope email", VERIFY_TTL)

    def login(self, email: str, password: str) -> NewSession | None:
        user = self.accounts.get_user_by_email(email)
        # Always run a hash verification so timing does not reveal whether the account exists.
        valid = verify_password(user.password_hash if user else None, password)
        if user is None or not valid or not user.active:
            return None
        if needs_rehash(user.password_hash):
            self.accounts.set_password(user.id, hash_password(password))
        return self._start_session(user)

    def refresh(self, old_session_id: str, user: UserRecord) -> NewSession:
        """Rotates the session token (and CSRF token), revoking the old one."""
        self.accounts.revoke_session(old_session_id)
        return self._start_session(user)

    def logout(self, session_id: str) -> None:
        self.accounts.revoke_session(session_id)

    def verify_email(self, token: str) -> str | None:
        user_id = self.accounts.consume_account_token("verify_email", token)
        if user_id:
            self.accounts.mark_email_verified(user_id)
        return user_id

    def request_password_reset(self, email: str) -> str | None:
        """Returns the user id if an account exists (for auditing). The API never reveals this."""
        user = self.accounts.get_user_by_email(email)
        if user is None or not user.active:
            return None
        self._send_link(
            user, "reset_password", "reset-password", "Reset your SecureScope password", RESET_TTL
        )
        return user.id

    def reset_password(self, token: str, password: str) -> str | None:
        user_id = self.accounts.consume_account_token("reset_password", token)
        if user_id is None:
            return None
        self.accounts.set_password(user_id, hash_password(password))
        self.accounts.revoke_all_sessions(user_id)  # a reset ends every existing session
        return user_id
