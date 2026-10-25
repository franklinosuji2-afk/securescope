"""The migration chain is one straight line. Two heads would make the container's start-up command fail and
take the service down, so a second head must be caught in CI, not at deploy time."""

from __future__ import annotations

from alembic.script import ScriptDirectory

from app.database.migrate import alembic_config


def test_there_is_exactly_one_migration_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    assert len(script.get_heads()) == 1


def test_every_migration_can_be_stepped_back_by_a_downgrade() -> None:
    """Rolling back is documented as "restore a backup", but a revision with no downgrade would also block the
    rehearsal that proves a release can be undone locally."""
    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    missing = [
        revision.revision
        for revision in script.walk_revisions()
        if not callable(getattr(revision.module, "downgrade", None))
    ]
    assert missing == []
