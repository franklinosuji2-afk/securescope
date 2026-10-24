"""When a scheduled scan finds something worth an email, and what the email says.

An alert is sent only when something changed for the worse: a finding that was not in the previous scan
(informational notes do not count), a score that fell by 5 points or more, or a scan that failed. A run that
finds the same things as last time sends nothing. Alerts go only to people who belong to the workspace.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.reporting.compare import compare_scans
from app.repositories.accounts import AccountRepository
from app.schemas.scan import Finding, ScanDetail, ScanStatus, Severity
from app.security.permissions import Role
from app.services.mailer import Mailer

if TYPE_CHECKING:
    from app.services.webhooks import WebhookService

logger = logging.getLogger("securescope.alerts")

SCORE_DROP_THRESHOLD = 5
RECIPIENT_ROLES = (Role.OWNER, Role.ADMIN, Role.SECURITY_ANALYST)
MAX_LISTED = 10


@dataclass(frozen=True)
class AlertDecision:
    send: bool
    subject: str = ""
    reasons: tuple[str, ...] = ()
    new_findings: tuple[Finding, ...] = ()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def decide(previous: ScanDetail | None, current: ScanDetail) -> AlertDecision:
    host = current.host
    if current.status == ScanStatus.FAILED:
        return AlertDecision(
            send=True,
            subject=f"SecureScope: the scheduled scan of {host} failed",
            reasons=("The scheduled scan could not be completed.",),
        )
    if current.status != ScanStatus.COMPLETED or previous is None:
        return AlertDecision(send=False)
    change = compare_scans(previous, current)
    new = tuple(f for f in change.new_findings if f.severity != Severity.INFO)
    reasons: list[str] = []
    if new:
        reasons.append(f"{_plural(len(new), 'new finding')} since the previous scan.")
    drop = -change.score_change if change.score_change is not None and change.score_change < 0 else 0
    if drop >= SCORE_DROP_THRESHOLD:
        reasons.append(f"The score fell by {drop} points to {current.score}.")
    if not reasons:
        return AlertDecision(send=False)
    lead = f"{_plural(len(new), 'new finding')} on {host}" if new else f"The score of {host} fell"
    return AlertDecision(send=True, subject=f"SecureScope: {lead}", reasons=tuple(reasons), new_findings=new)


def build_body(decision: AlertDecision, current: ScanDetail, base_url: str) -> str:
    lines = [f"SecureScope checked {current.host} on its schedule.", ""]
    lines += [f"- {reason}" for reason in decision.reasons]
    if decision.new_findings:
        lines += ["", "New findings:"]
        for f in decision.new_findings[:MAX_LISTED]:
            lines.append(f"  [{f.severity.value}] {f.title}")
        extra = len(decision.new_findings) - MAX_LISTED
        if extra > 0:
            lines.append(f"  and {extra} more")
    link = f"{base_url.rstrip('/')}/#/findings?scan={current.id}"
    lines += [
        "",
        f"Open the scan: {link}",
        "",
        "You get this email because you are an owner, admin or security analyst of the workspace. Scheduled "
        "scans and alerts can be changed on the Targets and Integrations pages. SecureScope sends an alert only when "
        "something changed for the worse.",
    ]
    return "\n".join(lines)


class AlertService:
    def __init__(
        self,
        accounts: AccountRepository,
        mailer: Mailer,
        settings: Settings,
        webhooks: WebhookService | None = None,
    ) -> None:
        self._accounts = accounts
        self._mailer = mailer
        self._settings = settings
        self._webhooks = webhooks

    def recipients(self, organization_id: str) -> list[str]:
        members = self._accounts.list_members(organization_id)
        return sorted({m.email for m in members if m.role in RECIPIENT_ROLES})

    def notify(self, organization_id: str, previous: ScanDetail | None, current: ScanDetail) -> int:
        """Sends the alert if there is one. Returns how many emails were sent."""
        decision = decide(previous, current)
        if not decision.send:
            return 0
        body = build_body(decision, current, self._settings.public_base_url)
        sent = 0
        for address in self.recipients(organization_id):
            try:
                self._mailer.send(address, decision.subject, body)
                sent += 1
            except Exception:  # a mail problem must never stop the scheduler  # noqa: BLE001
                logger.warning("alert email could not be sent")
        return sent

    async def notify_async(
        self, organization_id: str, previous: ScanDetail | None, current: ScanDetail
    ) -> int:
        """Email first, then the webhooks. Returns how many emails were sent."""
        sent = await asyncio.to_thread(self.notify, organization_id, previous, current)
        if self._webhooks is not None:
            decision = decide(previous, current)
            try:
                await self._webhooks.dispatch_alert(
                    organization_id, decision, current, self._settings.public_base_url
                )
            except Exception:  # a webhook problem must never stop the scheduler  # noqa: BLE001
                logger.warning("webhook alerts could not be sent")
        return sent
