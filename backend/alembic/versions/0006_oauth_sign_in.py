"""sign in with Google and GitHub

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_oauth_identities_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_identities"),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("state_hash", name="pk_oauth_states"),
    )


def downgrade() -> None:
    op.drop_table("oauth_states")
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
