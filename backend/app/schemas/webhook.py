"""Webhook endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WebhookOut(BaseModel):
    id: str
    # Scheme, host and port only. The path may hold a token, so it is not repeated.
    address: str
    enabled: bool
    last_attempt_at: datetime | None = None
    last_status: str | None = None
    consecutive_failures: int = 0
    created_at: datetime


class WebhookCreated(WebhookOut):
    # Shown once, when the endpoint is created or its secret is renewed.
    signing_secret: str


class WebhookList(BaseModel):
    available: bool  # the plan includes alerts
    configured: bool  # the server has a signing key
    limit: int
    items: list[WebhookOut]


class WebhookCreate(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class WebhookUpdate(BaseModel):
    enabled: bool


class WebhookTestResult(BaseModel):
    ok: bool
    status: str


class WebhookDeliveryOut(BaseModel):
    delivery_id: str
    event: str
    ok: bool
    status: str
    attempts: int
    created_at: datetime
