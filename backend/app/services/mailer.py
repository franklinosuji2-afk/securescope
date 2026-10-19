"""Outgoing mail.

`LogMailer` is for development only: it writes the message, including one-time links, to the log.
`ApiMailer` sends real email through a provider's HTTPS API (Brevo or Resend). Sending never raises into
the request: a provider outage must not break registration or password-reset requests, and the log
records only that a send failed (never the message body, the link or the API key).
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.logging import log_event

logger = logging.getLogger("securescope.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class LogMailer:
    """DEVELOPMENT ONLY. Writes the message (including one-time links) to the application log."""

    def send(self, to: str, subject: str, body: str) -> None:
        log_event(logger, "dev mail (not delivered)", to=to, subject=subject, body=body)


class ApiMailer:
    """Sends plain-text email through Brevo or Resend."""

    ENDPOINTS = {
        "brevo": "https://api.brevo.com/v3/smtp/email",
        "resend": "https://api.resend.com/emails",
    }

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if settings.mail_api_key is None or settings.mail_from_email is None:
            raise ValueError("a mail API key and sender address are required")
        self.provider = settings.mail_provider
        self._key = settings.mail_api_key.get_secret_value()
        self._from_email = settings.mail_from_email
        self._from_name = settings.mail_from_name
        self._client = httpx.Client(
            timeout=settings.mail_timeout_seconds, transport=transport, trust_env=False
        )

    def _request(self, to: str, subject: str, body: str) -> tuple[dict[str, str], dict[str, object]]:
        if self.provider == "brevo":
            headers = {"api-key": self._key, "accept": "application/json"}
            payload: dict[str, object] = {
                "sender": {"name": self._from_name, "email": self._from_email},
                "to": [{"email": to}],
                "subject": subject,
                "textContent": body,
            }
        else:
            headers = {"Authorization": f"Bearer {self._key}"}
            payload = {
                "from": f"{self._from_name} <{self._from_email}>",
                "to": [to],
                "subject": subject,
                "text": body,
            }
        return headers, payload

    def send(self, to: str, subject: str, body: str) -> None:
        headers, payload = self._request(to, subject, body)
        try:
            response = self._client.post(self.ENDPOINTS[self.provider], headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            log_event(
                logger,
                "mail send failed",
                provider=self.provider,
                status=status,
                error=type(exc).__name__,
            )
            return
        log_event(logger, "mail sent", provider=self.provider)


def build_mailer(settings: Settings) -> Mailer:
    return LogMailer() if settings.mail_provider == "log" else ApiMailer(settings)
