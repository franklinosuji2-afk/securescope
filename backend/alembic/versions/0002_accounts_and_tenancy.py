"""users, organizations, memberships, sessions, tokens, audit events; scans become org-scoped

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", TS),
        sa.Column("account_status", sa.String(16), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization_members"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_members_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_organization_members_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
    )
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("used_at", TS),
        sa.PrimaryKeyConstraint("id", name="pk_account_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_account_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_account_tokens_token_hash"),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("organization_id", sa.String(32)),
        sa.Column("actor_user_id", sa.String(32)),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("resource_type", sa.String(32)),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("timestamp", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_events_organization_id_organizations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_events_actor_user_id_users", ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_audit_events_organization_id_timestamp", "audit_events", ["organization_id", "timestamp"]
    )
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(32)))
        batch.add_column(sa.Column("requested_by", sa.String(32)))
        batch.create_foreign_key(
            "fk_scans_organization_id_organizations",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_scans_requested_by_users", "users", ["requested_by"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_scans_organization_id_created_at", ["organization_id", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.drop_index("ix_scans_organization_id_created_at")
        batch.drop_constraint("fk_scans_requested_by_users", type_="foreignkey")
        batch.drop_constraint("fk_scans_organization_id_organizations", type_="foreignkey")
        batch.drop_column("requested_by")
        batch.drop_column("organization_id")
    op.drop_index("ix_audit_events_organization_id_timestamp", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_account_tokens_user_id", table_name="account_tokens")
    op.drop_table("account_tokens")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("users")
