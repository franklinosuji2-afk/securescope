"""Runtime configuration, read from environment variables (prefix SECURESCOPE_)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECURESCOPE_", env_file=".env", extra="ignore")

    # Storage
    # PostgreSQL in Docker Compose/production. Tests may use SQLite; SQLite is not supported in production.
    database_url: str = "postgresql+psycopg://securescope:change-me@localhost:5432/securescope"
    retention_days: int = Field(30, ge=1, le=3650)

    # HTTP / CORS
    cors_origins: list[str] = ["http://localhost:8080", "http://localhost:5173"]
    trust_proxy_headers: bool = False

    # Scan safety limits (enforced server side)
    max_redirects: int = Field(5, ge=0, le=10)
    request_timeout_seconds: float = Field(8.0, gt=0, le=30)
    max_response_bytes: int = Field(262_144, ge=1024, le=2_097_152)
    max_requests_per_scan: int = Field(6, ge=1, le=20)
    max_scan_seconds: float = Field(25.0, gt=0, le=120)
    max_concurrent_scans: int = Field(3, ge=1, le=50)
    allowed_ports: list[int] = [80, 443, 8080, 8443]

    # Sessions and accounts
    session_ttl_hours: int = Field(12, ge=1, le=720)
    # Secure cookies need HTTPS. Docker Compose for local HTTP development turns this off explicitly.
    cookie_secure: bool = True
    login_attempts_per_ip_per_15min: int = Field(20, ge=1)
    login_attempts_per_email_per_15min: int = Field(5, ge=1)
    registrations_per_ip_per_hour: int = Field(10, ge=1)
    password_reset_requests_per_ip_per_hour: int = Field(5, ge=1)
    # Base URL used in verification/reset links written to the (development) mailer log.
    public_base_url: str = "http://localhost:8080"

    target_verifications_per_target_per_hour: int = Field(10, ge=1)

    # Abuse protection (per client address, in memory)
    scans_per_client_per_hour: int = Field(10, ge=1)
    scans_per_target_per_hour: int = Field(3, ge=1)

    # DANGEROUS: lets the scanner reach loopback/private addresses. Only for automated tests
    # against a local mock server. Never enable in a deployed environment.
    allow_private_targets: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
