"""Configuration that would silently weaken security is refused at start-up instead of accepted."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_DB = "postgresql+psycopg://app:a-long-random-value@db.example/securescope"


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "null", "  ", ""])
def test_cors_origins_must_be_exact(origin: str) -> None:
    with pytest.raises(ValidationError, match="exact origins"):
        Settings(database_url=GOOD_DB, cors_origins=[origin])


def test_exact_origins_are_accepted() -> None:
    s = Settings(database_url=GOOD_DB, cors_origins=["https://getsecurescope.com", "http://localhost:5173"])
    assert len(s.cors_origins) == 2


def test_the_placeholder_database_password_is_refused_on_a_public_https_address() -> None:
    with pytest.raises(ValidationError, match="placeholder password"):
        Settings(public_base_url="https://getsecurescope.com")  # the default URL carries the placeholder
    Settings(public_base_url="https://getsecurescope.com", database_url=GOOD_DB)
    Settings()  # local development and the test setup still work
