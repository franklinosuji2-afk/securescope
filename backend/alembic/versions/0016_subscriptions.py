"""Subscription state and handled billing events (groundwork; nothing writes them yet)

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column(
            "organization_id",
            sa.String(32),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_subscription_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("pending_plan_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_id"),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("provider_event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("organization_id", sa.String(32), sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_billing_events_provider_event"),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_table("subscriptions")
