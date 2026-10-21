"""stored PDF reports

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(32), nullable=False),  # the public report ID, e.g. SSR-7K3M9QX2TB
        sa.Column("scan_id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("generated_by", sa.String(32), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], name="fk_reports_scan_id_scans", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_reports_organization_id_organizations", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], name="fk_reports_generated_by_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.UniqueConstraint("scan_id", name="uq_reports_scan_id"),
    )
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_organization_id", table_name="reports")
    op.drop_table("reports")
