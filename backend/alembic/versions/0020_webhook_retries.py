"""Alerts that could not be delivered are retried later

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_retries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "webhook_id",
            sa.String(32),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delivery_id", sa.String(32), nullable=False),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("retries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_webhook_retries_next_attempt_at", "webhook_retries", ["next_attempt_at"])
    op.create_index("ix_webhook_retries_webhook_id", "webhook_retries", ["webhook_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_retries_webhook_id", table_name="webhook_retries")
    op.drop_index("ix_webhook_retries_next_attempt_at", table_name="webhook_retries")
    op.drop_table("webhook_retries")
