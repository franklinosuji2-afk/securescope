from __future__ import annotations

import os

import pytest
from sqlalchemy.pool import QueuePool

from app.core.config import Settings
from app.database.session import make_engine


def test_sqlite_keeps_its_defaults() -> None:
    engine = make_engine("sqlite://")
    assert not isinstance(engine.pool, QueuePool) or engine.pool.size() >= 1
    engine.dispose()


@pytest.mark.skipif("SECURESCOPE_TEST_DATABASE_URL" not in os.environ, reason="needs PostgreSQL")
def test_postgres_pool_is_small_and_bounded() -> None:
    engine = make_engine(
        os.environ["SECURESCOPE_TEST_DATABASE_URL"],
        pool_size=3,
        max_overflow=2,
        pool_timeout=7,
        pool_recycle=600,
        connect_timeout=4,
    )
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 3 and pool._max_overflow == 2 and pool._timeout == 7 and pool._recycle == 600
    assert engine.dialect.name == "postgresql"
    engine.dispose()


def test_pool_settings_have_safe_bounds() -> None:
    defaults = Settings(database_url="postgresql+psycopg://u:p@h/d")
    assert defaults.db_pool_size + defaults.db_max_overflow <= 20
    assert defaults.db_pool_timeout_seconds <= 60
    with pytest.raises(ValueError):
        Settings(database_url="postgresql+psycopg://u:p@h/d", db_pool_size=500)
