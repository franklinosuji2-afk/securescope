"""Platform Health responses (operator only)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    ok: bool
    latency_ms: int | None


class RouteStat(BaseModel):
    route: str
    requests: int
    errors: int
    p95_ms: int | None


class RequestWindow(BaseModel):
    window_seconds: float
    requests: int
    server_errors: int
    client_errors: int
    error_rate: float | None
    p50_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    routes: list[RouteStat]
    truncated: bool


class ScanHealth(BaseModel):
    window_hours: int
    completed: int
    failed: int
    cancelled: int
    in_progress: int
    avg_seconds: float | None
    max_concurrent: int
    running_here: int


class MailHealth(BaseModel):
    provider: str
    delivering: bool
    sent: int
    failed: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure_status: int | None


class Configuration(BaseModel):
    trusted_proxy: bool
    admin_email: bool
    analytics_enabled: bool
    metrics_endpoint: bool
    cookie_secure: bool
    verification_valid_days: int
    retention_days: int


class PlatformHealth(BaseModel):
    version: str
    started_at: datetime
    uptime_seconds: float
    database: DatabaseHealth
    requests: RequestWindow
    scans: ScanHealth
    mail: MailHealth
    configuration: Configuration
