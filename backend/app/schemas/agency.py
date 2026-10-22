from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CONTROL = {chr(c) for c in range(0, 32) if c not in (9, 10)} | {chr(127)}


def _clean(value: str) -> str:
    return "".join(ch for ch in value if ch not in _CONTROL).strip()


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    contact_email: str | None = Field(default=None, max_length=254)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "contact_email", "notes")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean(value)
        return cleaned or None

    @field_validator("name")
    @classmethod
    def name_required(cls, value: str | None) -> str:
        if not value:
            raise ValueError("A client needs a name.")
        return value

    @field_validator("contact_email")
    @classmethod
    def plausible_email(cls, value: str | None) -> str | None:
        if value is not None and ("@" not in value or " " in value):
            raise ValueError("Enter a valid email address.")
        return value


class ClientUpdate(ClientCreate):
    pass


class ClientOut(BaseModel):
    id: str
    name: str
    contact_email: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    site_count: int = 0


class ClientList(BaseModel):
    items: list[ClientOut]


class AssignClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str | None = Field(default=None, max_length=64)


class Branding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agency_name: str | None = Field(default=None, max_length=80)

    @field_validator("agency_name")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean(value) or None


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class DashboardSite(BaseModel):
    target_id: str
    hostname: str
    verified: bool
    last_scan_id: str | None = None
    last_scan_at: datetime | None = None
    score: int | None = None
    grade: str | None = None
    open_findings: SeverityCounts = SeverityCounts()


class DashboardClient(BaseModel):
    client_id: str | None  # None = websites not assigned to a client
    name: str
    sites: list[DashboardSite]
    open_findings: SeverityCounts
    worst_grade: str | None = None
    last_scan_at: datetime | None = None


class Dashboard(BaseModel):
    clients: list[DashboardClient]
    total_sites: int
    total_clients: int


ShareDays = Literal[7, 30, 90]


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: ShareDays = 30


class ShareOut(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    last_viewed_at: datetime | None = None
    view_count: int = 0
    status: Literal["active", "expired", "revoked"]


class ShareCreated(ShareOut):
    # Shown once. Only a hash of it is kept, so it cannot be shown again.
    token: str
    path: str


class ShareList(BaseModel):
    items: list[ShareOut]


class SharedReportInfo(BaseModel):
    host: str
    scanned_at: datetime
    score: int | None
    grade: str | None
    prepared_by: str | None
    expires_at: datetime
    download_path: str
