"""Alembic environment. The URL comes from the config object, or SECURESCOPE_DATABASE_URL."""

from __future__ import annotations

import os

from sqlalchemy import create_engine

from alembic import context
from app.database.base import Base
from app.models import account as _account  # noqa: F401  (registers tables on Base.metadata)
from app.models import agency as _agency  # noqa: F401
from app.models import analytics as _analytics  # noqa: F401
from app.models import billing as _billing  # noqa: F401
from app.models import feedback as _feedback  # noqa: F401
from app.models import scan as _scan  # noqa: F401
from app.models import schedule as _schedule  # noqa: F401
from app.models import target as _target  # noqa: F401

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("SECURESCOPE_DATABASE_URL")
    if not url:
        raise RuntimeError("Set SECURESCOPE_DATABASE_URL or pass sqlalchemy.url")
    return url.replace("%%", "%")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
