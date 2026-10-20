"""cookieless website analytics

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_views",
        sa.Column("row_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page", sa.String(32), nullable=False),
        sa.Column("referrer_host", sa.String(255)),
        sa.Column("device", sa.String(8), nullable=False),
        sa.Column("visitor", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("row_id", name="pk_page_views"),
    )
    op.create_index("ix_page_views_occurred_at", "page_views", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_page_views_occurred_at", table_name="page_views")
    op.drop_table("page_views")
