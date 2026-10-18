"""Outgoing mail. v0.3 ships only a development mailer that writes the message to the log.

Real delivery (SMTP or a provider API) is not implemented. A link in the log is NOT a sent email:
the product must not claim email verification or password recovery works for real users until a
production mailer exists. See docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.logging import log_event

logger = logging.getLogger("securescope.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class LogMailer:
    """DEVELOPMENT ONLY. Writes the message (including one-time links) to the application log."""

    def send(self, to: str, subject: str, body: str) -> None:
        log_event(logger, "dev mail (not delivered)", to=to, subject=subject, body=body)
