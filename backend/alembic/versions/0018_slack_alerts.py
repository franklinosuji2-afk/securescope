"""Webhook endpoints can be Slack incoming webhooks

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webhook_endpoints",
        sa.Column("kind", sa.String(8), nullable=False, server_default="webhook"),
    )


def downgrade() -> None:
    op.drop_column("webhook_endpoints", "kind")
