"""initial scans and findings

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("grade", sa.String(2)),
        sa.Column("error", sa.Text()),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("authorization_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_scans"),
    )
    op.create_index("ix_scans_created_at", "scans", ["created_at"])
    op.create_table(
        "findings",
        sa.Column("row_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("finding_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("row_id", name="pk_findings"),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_findings_scan_id_scans", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_findings_scan_id_position", "findings", ["scan_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_findings_scan_id_position", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_scans_created_at", table_name="scans")
    op.drop_table("scans")
