"""Invitations to join an organization, sent by email as a single-use link."""

from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.repositories.accounts import AccountRepository, InvitationRecord, UserRecord
from app.security.permissions import Role
from app.security.tokens import new_token
from app.services.mailer import Mailer

INVITATION_TTL = timedelta(days=7)
MAX_PENDING_PER_ORGANIZATION = 50

ROLE_TEXT = {
    Role.VIEWER: "a viewer, who can read scans, findings and reports but cannot change anything",
    Role.MEMBER: "a member, who can read results and start scans",
    Role.SECURITY_ANALYST: "a security analyst",
    Role.ADMIN: "an administrator",
    Role.OWNER: "an owner",
}


class InvitationService:
    def __init__(self, accounts: AccountRepository, settings: Settings, mailer: Mailer) -> None:
        self.accounts = accounts
        self.settings = settings
        self.mailer = mailer

    def invite(
        self, organization_id: str, email: str, role: Role, inviter: UserRecord
    ) -> InvitationRecord:
        token = new_token()
        record = self.accounts.create_invitation(organization_id, email, role, inviter.id, token, INVITATION_TTL)
        link = f"{self.settings.public_base_url.rstrip('/')}/accept-invite?token={token}"
        body = (
            f"{inviter.email} invited you to join the workspace \"{record.organization_name}\" on SecureScope "
            f"as {ROLE_TEXT[role]}.\n\n"
            f"Open this link to accept (valid for {INVITATION_TTL.days} days, works once):\n{link}\n\n"
            f"Sign in or create an account with this email address ({record.email}); the invitation only works "
            "for that address.\n\n"
            "If you were not expecting this, you can ignore this message. Nothing happens unless you accept."
        )
        self.mailer.send(record.email, f"You are invited to {record.organization_name} on SecureScope", body)
        return record
