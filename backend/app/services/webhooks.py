"""Webhook alerts: a signed JSON message to the addresses a workspace has chosen.

Safety rules, in the order they matter:
- The address is checked when it is saved and again before every delivery (so a name that later points at an
  internal address is refused), and the connection is pinned to the checked address.
- Only https is accepted. Redirects are not followed. The reply body is never read.
- Each message is signed with HMAC-SHA256 over "<timestamp>.<body>". The signing secret of an endpoint is
  derived from the server's key, so no secret is stored in the database; the receiver sees it once.
- A failure never stops a scan or an email: it is recorded on the endpoint and, after ten failures in a row,
  the endpoint is switched off until a person switches it on again.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.repositories.webhooks import Endpoint, WebhookRepository
from app.schemas.scan import ScanDetail
from app.security.target import TargetError, validate_target
from app.services.alerts import AlertDecision

logger = logging.getLogger("securescope.webhooks")

USER_AGENT = "SecureScope-Webhook/1"
MAX_ATTEMPTS = 2
MAX_FINDINGS_LISTED = 20
# A Slack incoming webhook: the one host and the one path shape Slack uses, nothing else.
SLACK_ADDRESS = re.compile(
    r"^https://hooks\.slack\.com/services/[A-Z0-9]{8,}/[A-Z0-9]{8,}/[A-Za-z0-9]{16,}\Z"
)
SECRET_PREFIX = "whsec_"  # noqa: S105  # nosec B105 (a label, not a secret)


def _slack_escape(text: str) -> str:
    """Slack treats &, < and > as markup, so any text we did not write ourselves is escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_text(event: str, payload: dict[str, Any]) -> str:
    """The Slack message for an event: plain text, the same facts as the signed webhook and nothing more."""
    if event != "scan.alert":
        return f"SecureScope: {_slack_escape(str(payload.get('message', 'Test message.')))}"
    site = payload.get("site", {}).get("host", "a site")
    scan = payload.get("scan", {})
    lines = [f":warning: *SecureScope alert for {_slack_escape(str(site))}*"]
    lines += [f"• {_slack_escape(str(r))}" for r in payload.get("reasons", [])]
    for f in payload.get("new_findings", [])[:MAX_FINDINGS_LISTED]:
        lines.append(f"    [{_slack_escape(str(f.get('severity')))}] {_slack_escape(str(f.get('title')))}")
    if scan.get("score") is not None:
        lines.append(f"Score {scan['score']} (grade {_slack_escape(str(scan.get('grade')))})")
    if scan.get("url"):
        lines.append(f"<{scan['url']}|Open the scan in SecureScope>")
    return "\n".join(lines)


class WebhookService:
    def __init__(
        self,
        repo: WebhookRepository,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delay: float = 1.0,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self.transport = transport
        self.retry_delay = retry_delay

    @property
    def configured(self) -> bool:
        return self._settings.webhook_signing_key is not None

    def secret_for(self, endpoint: Endpoint) -> str:
        key = self._settings.webhook_signing_key
        if key is None:
            raise RuntimeError("webhook signing key is not configured")
        info = f"webhook:{endpoint.id}:{endpoint.key_version}".encode()
        digest = hmac.new(key.get_secret_value().encode(), info, hashlib.sha256).hexdigest()
        return f"{SECRET_PREFIX}{digest}"

    @staticmethod
    def sign(secret: str, timestamp: int, body: bytes) -> str:
        signed = f"{timestamp}.".encode() + body
        return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()

    async def validate_address(self, url: str, kind: str = "webhook") -> str:
        """Returns the cleaned address or raises TargetError with a message that is safe to show."""
        candidate = url.strip()
        if kind == "slack" and not SLACK_ADDRESS.match(candidate):
            raise TargetError(
                "That is not a Slack incoming-webhook address. It looks like "
                "https://hooks.slack.com/services/T…/B…/… and is created in your Slack app settings."
            )
        if not candidate.lower().startswith("https://"):
            raise TargetError("The address must start with https://.")
        target = await validate_target(candidate, self._settings)
        if target.scheme != "https":
            raise TargetError("The address must start with https://.")
        return candidate

    async def _post_once(
        self, endpoint: Endpoint, body: bytes, event: str, delivery_id: str
    ) -> tuple[bool, bool, str]:
        """(delivered, worth retrying, status text)."""
        try:
            target = await validate_target(endpoint.url, self._settings)
        except TargetError as exc:
            return False, False, f"Blocked: {exc}"[:120]
        if target.scheme != "https":
            return False, False, "Blocked: the address is not https."
        if endpoint.kind == "slack" and not SLACK_ADDRESS.match(endpoint.url):
            return False, False, "Blocked: the address is not a Slack incoming webhook."
        host = target.host if target.port in (80, 443) else f"{target.host}:{target.port}"
        headers = {
            "Host": host,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        }
        if endpoint.kind != "slack":
            timestamp = int(time.time())
            signature = self.sign(self.secret_for(endpoint), timestamp, body)
            headers["X-SecureScope-Event"] = event
            headers["X-SecureScope-Delivery"] = delivery_id
            headers["X-SecureScope-Signature"] = f"t={timestamp},v1={signature}"
        ip = ipaddress.ip_address(target.addresses[0])
        shown = f"[{ip}]" if ip.version == 6 else str(ip)
        pinned = f"https://{shown}:{target.port}{target.path_and_query}"
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(self._settings.request_timeout_seconds),
                    follow_redirects=False,
                    verify=True,
                    transport=self.transport,
                    trust_env=False,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
                ) as client,
                client.stream(
                    "POST", pinned, content=body, headers=headers, extensions={"sni_hostname": target.host}
                ) as response,
            ):
                code = response.status_code
        except httpx.TimeoutException:
            return False, True, "Failed: the request timed out."
        except httpx.HTTPError:
            return False, True, "Failed: could not connect."
        if 200 <= code < 300:
            return True, False, f"Delivered (HTTP {code})"
        retry = code >= 500 or code == 429
        note = " Redirects are not followed." if 300 <= code < 400 else ""
        return False, retry, f"Failed (HTTP {code}).{note}"

    async def deliver(self, endpoint: Endpoint, event: str, data: dict[str, Any]) -> tuple[bool, str]:
        delivery_id = uuid.uuid4().hex
        payload = {
            "event": event,
            "delivery_id": delivery_id,
            "created_at": datetime.now(UTC).isoformat(),
            **data,
        }
        shown = {"text": slack_text(event, payload)} if endpoint.kind == "slack" else payload
        body = json.dumps(shown, separators=(",", ":"), ensure_ascii=False).encode()
        ok, status = False, "Not sent"
        attempts = 0
        for attempt in range(MAX_ATTEMPTS):
            attempts += 1
            ok, retry, status = await self._post_once(endpoint, body, event, delivery_id)
            if ok or not retry or attempt == MAX_ATTEMPTS - 1:
                break
            await asyncio.sleep(self.retry_delay)
        await asyncio.to_thread(
            functools.partial(
                self._repo.record_attempt,
                endpoint.id,
                ok,
                status,
                event=event,
                delivery_id=delivery_id,
                attempts=attempts,
            )
        )
        return ok, status

    async def send_test(self, endpoint: Endpoint) -> tuple[bool, str]:
        return await self.deliver(
            endpoint,
            "webhook.test",
            {"message": "This is a test message from SecureScope. No scan or finding is involved."},
        )

    async def dispatch_alert(
        self, organization_id: str, decision: AlertDecision, current: ScanDetail, base_url: str
    ) -> int:
        """Sends the alert to every enabled endpoint. Returns how many were delivered."""
        if not self.configured or not decision.send:
            return 0
        endpoints = await asyncio.to_thread(self._repo.endpoints, organization_id, only_enabled=True)
        if not endpoints:
            return 0
        data: dict[str, Any] = {
            "site": {"host": current.host},
            "scan": {
                "id": current.id,
                "status": current.status.value,
                "score": current.score,
                "grade": current.grade,
                "url": f"{base_url.rstrip('/')}/#/findings?scan={current.id}",
            },
            "reasons": list(decision.reasons),
            "new_findings": [
                {"id": f.id, "severity": f.severity.value, "title": f.title}
                for f in decision.new_findings[:MAX_FINDINGS_LISTED]
            ],
        }
        results = await asyncio.gather(
            *(self._safe_deliver(e, "scan.alert", data) for e in endpoints), return_exceptions=False
        )
        return sum(1 for ok in results if ok)

    async def _safe_deliver(self, endpoint: Endpoint, event: str, data: dict[str, Any]) -> bool:
        try:
            ok, _ = await self.deliver(endpoint, event, data)
            return ok
        except Exception:  # a webhook problem must never stop the scheduler  # noqa: BLE001
            logger.warning("webhook delivery failed unexpectedly")
            return False
