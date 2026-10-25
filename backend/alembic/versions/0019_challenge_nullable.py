"""Verification challenges can be cleared once used, removed or expired

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("targets") as batch:
        batch.alter_column("challenge_token", existing_type=sa.String(64), nullable=True)
        batch.alter_column("challenge_expires_at", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    # Rows without a challenge get a dead, already-expired one so the NOT NULL constraint can return.
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "UPDATE targets SET challenge_token = hex(randomblob(16)), challenge_expires_at = CURRENT_TIMESTAMP "
            "WHERE challenge_token IS NULL OR challenge_expires_at IS NULL"
        )
    else:
        op.execute(
            "UPDATE targets SET challenge_token = md5(random()::text || id), challenge_expires_at = now() "
            "WHERE challenge_token IS NULL OR challenge_expires_at IS NULL"
        )
    with op.batch_alter_table("targets") as batch:
        batch.alter_column("challenge_expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("challenge_token", existing_type=sa.String(64), nullable=False)
