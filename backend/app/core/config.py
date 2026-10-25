"""Runtime configuration, read from environment variables (prefix SECURESCOPE_)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ORIGIN = re.compile(
    r"^https?://(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*|\[[0-9a-f:]+\])(?::[0-9]{1,5})?$"
)


def _is_exact_origin(origin: str) -> bool:
    return bool(_ORIGIN.fullmatch(origin))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECURESCOPE_", env_file=".env", extra="ignore")

    # Storage
    # PostgreSQL in Docker Compose/production. Tests may use SQLite; SQLite is not supported in production.
    database_url: str = "postgresql+psycopg://securescope:change-me@localhost:5432/securescope"

    # HTTP / CORS
    cors_origins: list[str] = ["http://localhost:8080", "http://localhost:5173"]
    # Legacy switch: trusts the first X-Forwarded-For entry. Anyone who can reach the app directly can forge
    # it, so leave it off unless the app is reachable ONLY through a proxy you control.
    trust_proxy_headers: bool = False
    # Safer for a public deployment: a front proxy (the Cloudflare Pages Function) sends the visitor's
    # address in `client_ip_header` together with this shared secret in X-Proxy-Secret. The address is
    # used only when the secret matches, so a visitor who calls the backend directly cannot choose it.
    trusted_proxy_secret: SecretStr | None = None
    client_ip_header: str = "x-real-client-ip"

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
    # A new account must confirm its email address before it can use the dashboard (targets, scans,
    # results, reports). Turn this off only for local development or tests.
    require_verified_email: bool = True
    # PDF download links are signed and expire. The key is optional: without one a random key is made at
    # start-up, so links stop working after a restart (users simply ask for a new one).
    download_signing_key: SecretStr | None = None
    download_url_ttl_seconds: int = Field(300, ge=30, le=3600)
    # Shared secret for the scheduler: the Cloudflare cron presents it to POST /api/v1/internal/run-due. Without
    # it the endpoint does not exist (404), so scheduled scans are simply off.
    cron_secret: SecretStr | None = None
    # Master key for webhook signatures. Each endpoint's signing secret is derived from it, so no secret is
    # stored in the database. Without it the webhook feature is switched off (it says so plainly).
    webhook_signing_key: SecretStr | None = None
    # Base URL used in verification/reset links written to the (development) mailer log.
    public_base_url: str = "http://localhost:8080"

    # Outgoing mail. "log" only writes messages to the log (development). "brevo" and "resend" send real
    # email through the provider's HTTPS API. The key is a secret: set it in the host's environment only.
    mail_provider: Literal["log", "brevo", "resend"] = "log"
    mail_api_key: SecretStr | None = None
    mail_from_email: str | None = None
    mail_from_name: str = "SecureScope"
    # Optional address that replies go to (for example a support mailbox). Not a secret.
    mail_reply_to: str | None = None
    mail_timeout_seconds: float = Field(10.0, gt=0, le=30)

    # Sign in with Google / GitHub. Each provider is offered only when both its id and secret are set (a
    # half-set provider stays off and a warning is logged). The secrets belong in the host's environment only. Register this redirect URI with the provider:
    # {SECURESCOPE_PUBLIC_BASE_URL}/api/v1/auth/oauth/<provider>/callback
    oauth_google_client_id: str | None = None
    oauth_google_client_secret: SecretStr | None = None
    oauth_github_client_id: str | None = None
    oauth_github_client_secret: SecretStr | None = None
    oauth_attempts_per_ip_per_15min: int = Field(30, ge=1)

    target_verifications_per_target_per_hour: int = Field(10, ge=1)
    # How long a proven domain stays authorised before it must be proven again. 0 means it never expires.
    target_verification_valid_days: int = Field(180, ge=0, le=3650)

    # Website analytics (cookieless, public pages only). Only the signed-in account with this email
    # address, once confirmed, may read it. Leave empty to switch the dashboards off for everyone.
    admin_email: str | None = None
    # Plan for organizations that have none assigned. Production leaves this unset (Free); tests set it.
    default_plan: str | None = None
    analytics_enabled: bool = True
    # Mixed into the daily visitor hash. Set a long random value so the hash cannot be reproduced from
    # an address and browser string alone; if empty a random value is generated at start-up.
    analytics_salt: SecretStr | None = None
    analytics_retention_days: int = Field(90, ge=1, le=730)
    # How long audit-log entries are kept. Older entries are deleted by the hourly maintenance job.
    audit_retention_days: int = Field(365, ge=30, le=3650)
    analytics_events_per_client_per_hour: int = Field(60, ge=1)

    # Database connection pool (PostgreSQL). Total connections per process = pool size + overflow.
    db_pool_size: int = Field(5, ge=1, le=20)
    db_max_overflow: int = Field(5, ge=0, le=20)
    db_pool_timeout_seconds: float = Field(10.0, gt=0, le=60)
    db_pool_recycle_seconds: int = Field(1800, ge=30)
    db_connect_timeout_seconds: int = Field(10, ge=1, le=60)

    # Interactive API documentation (/api/docs, /api/openapi.json). Off by default: the page loads scripts from a
    # public CDN and the site and API share one origin, so production must not serve it. Local development only.
    api_docs_enabled: bool = False

    # Bearer token for GET /metrics (Prometheus format). Without it the endpoint does not exist (404).
    metrics_token: SecretStr | None = None

    # Abuse protection (per client address, in memory)
    scans_per_client_per_hour: int = Field(10, ge=1)
    scans_per_target_per_hour: int = Field(3, ge=1)

    # DANGEROUS: lets the scanner reach loopback/private addresses. Only for automated tests
    # against a local mock server. Never enable in a deployed environment.
    allow_private_targets: bool = False

    @model_validator(mode="after")
    def _mail_is_complete(self) -> Settings:
        if self.mail_provider != "log" and not (self.mail_api_key and self.mail_from_email):
            raise ValueError("mail_provider needs SECURESCOPE_MAIL_API_KEY and SECURESCOPE_MAIL_FROM_EMAIL")
        if self.cron_secret is not None and len(self.cron_secret.get_secret_value()) < 32:
            raise ValueError("SECURESCOPE_CRON_SECRET must be at least 32 characters")
        if self.webhook_signing_key is not None and len(self.webhook_signing_key.get_secret_value()) < 32:
            raise ValueError("SECURESCOPE_WEBHOOK_SIGNING_KEY must be at least 32 characters")
        # Cookies are sent with cross-origin requests from the listed sites, so every entry must be one exact
        # origin: scheme://host[:port], lower case, no path or trailing slash, no wildcard. A browser's Origin
        # header never matches anything else, so a loose entry would silently break sign-in instead.
        for origin in self.cors_origins:
            if not _is_exact_origin(origin):
                raise ValueError(
                    "SECURESCOPE_CORS_ORIGINS must list exact origins such as https://example.com "
                    "(lower case, no path, no trailing slash, no wildcards, not 'null')"
                )
        if self.allow_private_targets and (
            self.cookie_secure or self.public_base_url.lower().startswith("https://")
        ):
            raise ValueError(
                "SECURESCOPE_ALLOW_PRIVATE_TARGETS lets the scanner reach internal addresses and is for local "
                "tests only. It cannot be combined with secure cookies or an https public address."
            )
        if (
            self.public_base_url.lower().startswith("https://")
            and "change-me" in self.database_url.lower()
            and not self.database_url.startswith("sqlite")
        ):
            raise ValueError("SECURESCOPE_DATABASE_URL still contains the placeholder password 'change-me'")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
