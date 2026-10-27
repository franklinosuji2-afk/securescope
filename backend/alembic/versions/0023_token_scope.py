"""API token scope and expiry, and the token behind an App Scanning run

Revision ID: 0023
Revises: 0022

Additive and backwards compatible:
- api_tokens.scope is NOT NULL with the server default 'web', so every existing token (and any token written by
  the previous release) is a Web Scanning token exactly as before. No existing token gains App Scanning access.
- api_tokens.expires_at is NULL for existing tokens (they never expire, as before). Only new App Scanning tokens
  get an expiry.
- app_scans.token_id records which token submitted a run, for the per-token hourly limit. Nullable, set to NULL
  when the token is deleted.
"""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_tokens") as batch:
        batch.add_column(sa.Column("scope", sa.String(16), nullable=False, server_default="web"))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("app_scans") as batch:
        batch.add_column(sa.Column("token_id", sa.String(32), nullable=True))
        batch.create_foreign_key(
            "fk_app_scans_token_id_api_tokens", "api_tokens", ["token_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_app_scans_token_id_created_at", ["token_id", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("app_scans") as batch:
        batch.drop_index("ix_app_scans_token_id_created_at")
        batch.drop_constraint("fk_app_scans_token_id_api_tokens", type_="foreignkey")
        batch.drop_column("token_id")
    # App Scanning tokens cannot exist in a schema without scopes; remove them rather than turn them into
    # Web Scanning tokens, which would silently broaden what they can do.
    op.execute("DELETE FROM api_tokens WHERE scope <> 'web'")
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_column("expires_at")
        batch.drop_column("scope")
