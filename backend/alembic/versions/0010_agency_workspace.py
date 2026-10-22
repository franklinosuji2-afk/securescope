"""agency workspace: clients, report branding, shared report links

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("contact_email", sa.String(254), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_clients_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.UniqueConstraint("organization_id", "name", name="uq_clients_organization_id_name"),
    )
    op.create_index("ix_clients_organization_id", "clients", ["organization_id"])
    with op.batch_alter_table("targets") as batch:
        batch.add_column(sa.Column("client_id", sa.String(32), nullable=True))
        batch.create_foreign_key(
            "fk_targets_client_id_clients", "clients", ["client_id"], ["id"], ondelete="SET NULL"
        )
    op.create_table(
        "organization_branding",
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("agency_name", sa.String(80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_branding_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", name="pk_organization_branding"),
    )
    op.create_table(
        "report_shares",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("scan_id", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_report_shares_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_report_shares_scan_id_scans", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_report_shares_created_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_report_shares"),
        sa.UniqueConstraint("token_hash", name="uq_report_shares_token_hash"),
    )
    op.create_index("ix_report_shares_scan_id", "report_shares", ["scan_id"])


def downgrade() -> None:
    op.drop_index("ix_report_shares_scan_id", table_name="report_shares")
    op.drop_table("report_shares")
    op.drop_table("organization_branding")
    with op.batch_alter_table("targets") as batch:
        batch.drop_constraint("fk_targets_client_id_clients", type_="foreignkey")
        batch.drop_column("client_id")
    op.drop_index("ix_clients_organization_id", table_name="clients")
    op.drop_table("clients")
