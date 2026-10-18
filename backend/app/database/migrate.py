"""Programmatic access to Alembic so tests and the container entrypoint share one code path."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def main() -> None:
    """`python -m app.database.migrate` – used by the container entrypoint."""
    from app.core.config import get_settings

    upgrade(get_settings().database_url)


if __name__ == "__main__":
    main()
