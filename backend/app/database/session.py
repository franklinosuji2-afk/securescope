"""Engine and session factory. The same code runs on PostgreSQL (production) and SQLite (tests)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(
    url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_timeout: float = 10.0,
    pool_recycle: int = 1800,
    connect_timeout: int = 10,
) -> Engine:
    """PostgreSQL gets an explicit, small pool so a burst cannot open more connections than a free database
    allows, a request waits at most `pool_timeout` seconds for one, idle connections are replaced after
    `pool_recycle` seconds (a free database closes them when it pauses) and a dead host fails within
    `connect_timeout` seconds instead of hanging."""
    if url.startswith("postgresql"):
        engine = create_engine(
            url,
            pool_pre_ping=True,
            future=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            connect_args={"connect_timeout": connect_timeout},
        )
    else:
        engine = create_engine(url, pool_pre_ping=True, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
