"""App Scanning projects and runs (additive; no existing table changes)

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(32),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "name", name="uq_app_projects_organization_id_name"),
    )
    op.create_index("ix_app_projects_organization_id", "app_projects", ["organization_id"])
    op.create_table(
        "app_scans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(32),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id", sa.String(32), sa.ForeignKey("app_projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("requested_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("kinds_json", sa.Text, nullable=False),
        sa.Column("checks_run_json", sa.Text),
        sa.Column("checks_skipped_json", sa.Text),
        sa.Column("inputs_json", sa.Text),
        sa.Column("scanners_json", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("ref", sa.String(120)),
        sa.Column("idempotency_key", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_app_scans_organization_id_created_at", "app_scans", ["organization_id", "created_at"])
    op.create_index("ix_app_scans_project_id_created_at", "app_scans", ["project_id", "created_at"])
    op.create_index(
        "uq_app_scans_organization_id_idempotency_key",
        "app_scans",
        ["organization_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_app_scans_organization_id_idempotency_key", table_name="app_scans")
    op.drop_index("ix_app_scans_project_id_created_at", table_name="app_scans")
    op.drop_index("ix_app_scans_organization_id_created_at", table_name="app_scans")
    op.drop_table("app_scans")
    op.drop_index("ix_app_projects_organization_id", table_name="app_projects")
    op.drop_table("app_projects")
