"""API tokens and site badges

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_api_tokens_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_api_tokens_created_by_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
    )
    op.create_index("ix_api_tokens_organization_id", "api_tokens", ["organization_id"])
    op.create_table(
        "site_badges",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(32), nullable=False),
        sa.Column("token", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_site_badges_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["targets.id"], name="fk_site_badges_target_id_targets", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_badges"),
        sa.UniqueConstraint("target_id", name="uq_site_badges_target_id"),
        sa.UniqueConstraint("token", name="uq_site_badges_token"),
    )
    op.create_index("ix_site_badges_organization_id", "site_badges", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_site_badges_organization_id", table_name="site_badges")
    op.drop_table("site_badges")
    op.drop_index("ix_api_tokens_organization_id", table_name="api_tokens")
    op.drop_table("api_tokens")
