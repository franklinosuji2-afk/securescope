"""targets with domain-ownership challenges; scans reference the verified target

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("challenge_token", sa.String(64), nullable=False),
        sa.Column("challenge_expires_at", TS, nullable=False),
        sa.Column("verified_at", TS),
        sa.Column("verification_method", sa.String(16)),
        sa.Column("last_check_at", TS),
        sa.Column("last_check_error", sa.Text()),
        sa.Column("created_by", sa.String(32)),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_targets"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_targets_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_targets_created_by_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("organization_id", "hostname", name="uq_targets_organization_id_hostname"),
    )
    op.create_index("ix_targets_organization_id", "targets", ["organization_id"])
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("target_id", sa.String(32)))
        batch.create_foreign_key(
            "fk_scans_target_id_targets", "targets", ["target_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.drop_constraint("fk_scans_target_id_targets", type_="foreignkey")
        batch.drop_column("target_id")
    op.drop_index("ix_targets_organization_id", table_name="targets")
    op.drop_table("targets")
