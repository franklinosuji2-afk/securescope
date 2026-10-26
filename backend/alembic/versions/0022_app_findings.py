"""App Scanning findings (additive)

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_findings",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "scan_id", sa.String(32), sa.ForeignKey("app_scans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("confidence", sa.String(8), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("remediation", sa.Text, nullable=False),
        sa.Column("evidence", sa.Text),
        sa.Column("path", sa.String(255)),
        sa.Column("line", sa.Integer),
        sa.Column("ecosystem", sa.String(16)),
        sa.Column("package_name", sa.String(214)),
        sa.Column("package_version", sa.String(64)),
        sa.Column("fixed_versions_json", sa.Text),
        sa.Column("references_json", sa.Text),
        sa.Column("aliases_json", sa.Text),
        sa.Column("fingerprint", sa.String(64), nullable=False),
    )
    op.create_index("ix_app_findings_scan_id_position", "app_findings", ["scan_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_app_findings_scan_id_position", table_name="app_findings")
    op.drop_table("app_findings")
