"""Creating, storing and handing out PDF reports.

A report is made once per scan and kept. It is never served from a fixed address: the API hands the
signed-in user a short-lived link that is tied to that user, that organization and that report, and the
download route checks the signature, the session and the organization membership again.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.reporting.pdf import render_pdf
from app.repositories.reports import ReportMeta, ReportRepository, new_report_id
from app.schemas.scan import ScanDetail


def _signature(key: bytes, report_id: str, user_id: str, organization_id: str, expires: int) -> str:
    message = f"{report_id}|{user_id}|{organization_id}|{expires}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class DownloadLink:
    expires: int
    signature: str


class ReportService:
    def __init__(
        self,
        reports: ReportRepository,
        settings: Settings,
        key: bytes,
        prepared_by: Callable[[str], str | None] | None = None,
    ) -> None:
        self.reports = reports
        self._prepared_by = prepared_by
        self.settings = settings
        self._key = key

    def ensure_report(self, detail: ScanDetail, organization_id: str, user_id: str) -> ReportMeta:
        existing = self.reports.get_meta(detail.id, organization_id)
        if existing is not None:
            return existing
        report_id = new_report_id()
        brand = self._prepared_by(organization_id) if self._prepared_by else None
        rendered = render_pdf(detail, report_id, prepared_by=brand)
        return self.reports.save(rendered.report_id, detail.id, organization_id, user_id, rendered.content)

    def sign(self, report_id: str, user_id: str, organization_id: str) -> DownloadLink:
        expires = int(time.time()) + self.settings.download_url_ttl_seconds
        return DownloadLink(expires, _signature(self._key, report_id, user_id, organization_id, expires))

    def is_valid(
        self, report_id: str, user_id: str, organization_id: str, expires: int, signature: str
    ) -> bool:
        if expires < int(time.time()):
            return False
        expected = _signature(self._key, report_id, user_id, organization_id, expires)
        return hmac.compare_digest(expected, signature)
