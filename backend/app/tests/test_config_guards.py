"""Configuration that would silently weaken security is refused at start-up instead of accepted."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_DB = "postgresql+psycopg://app:a-long-random-value@db.example/securescope"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "null",
        "  ",
        "",
        "https://example.com/",  # a trailing slash never matches a browser's Origin header
        "https://example.com/app",
        "https://example.com?x=1",
        "HTTPS://EXAMPLE.COM",
        "ftp://example.com",
        "example.com",
        "https://user@example.com",
        "https://example.com:99999x",
    ],
)
def test_cors_origins_must_be_exact(origin: str) -> None:
    with pytest.raises(ValidationError, match="exact origins"):
        Settings(database_url=GOOD_DB, cors_origins=[origin])


def test_exact_origins_are_accepted() -> None:
    origins = [
        "https://getsecurescope.com",
        "http://localhost:5173",
        "https://app.example.co.uk:8443",
        "http://[::1]:8080",
    ]
    assert Settings(database_url=GOOD_DB, cors_origins=origins).cors_origins == origins


def test_an_empty_origin_list_is_allowed_for_a_same_origin_deployment() -> None:
    assert Settings(database_url=GOOD_DB, cors_origins=[]).cors_origins == []


def test_the_placeholder_database_password_is_refused_on_a_public_https_address() -> None:
    with pytest.raises(ValidationError, match="placeholder password"):
        Settings(public_base_url="https://getsecurescope.com")  # the default URL carries the placeholder
    with pytest.raises(ValidationError, match="placeholder password"):
        Settings(
            public_base_url="https://getsecurescope.com",
            database_url="postgresql+psycopg://securescope:Change-Me@db.example/securescope",
        )
    Settings(public_base_url="https://getsecurescope.com", database_url=GOOD_DB)
    Settings()  # local development and the test setup still work
