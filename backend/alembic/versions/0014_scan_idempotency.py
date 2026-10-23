"""Idempotency keys for scan creation

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("idempotency_key", sa.String(80), nullable=True))
    # Several rows may have no key (NULL); a key can be used once per workspace.
    op.create_index(
        "uq_scans_organization_id_idempotency_key",
        "scans",
        ["organization_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_scans_organization_id_idempotency_key", table_name="scans")
    op.drop_column("scans", "idempotency_key")
