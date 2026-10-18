"""Audit log responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    event_type: str
    actor_user_id: str | None
    actor_email: str | None
    resource_type: str | None
    resource_id: str | None
    request_id: str | None


class AuditList(BaseModel):
    items: list[AuditEntry]
    total: int
    # Every event type this organization has recorded, for the filter control.
    event_types: list[str]
