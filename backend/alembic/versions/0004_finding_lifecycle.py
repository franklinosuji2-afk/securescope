"""finding fingerprint and confidence; per-organization finding states

Revision ID: 0004
Revises: 0003
"""

import hashlib
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
HEURISTIC_IDS = ("SS-DIR-001",)


def _fingerprint(host: str, finding_id: str) -> str:
    return hashlib.sha256(f"{host.lower()}|{finding_id}".encode()).hexdigest()[:32]


def upgrade() -> None:
    op.add_column("findings", sa.Column("confidence", sa.String(8), nullable=False, server_default="high"))
    op.add_column("findings", sa.Column("fingerprint", sa.String(64)))
    op.create_table(
        "finding_states",
        sa.Column("row_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(32), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("finding_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("first_seen_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("resolved_at", TS),
        sa.Column("updated_by", sa.String(32)),
        sa.Column("updated_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("row_id", name="pk_finding_states"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_finding_states_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_finding_states_updated_by_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("organization_id", "fingerprint", name="uq_finding_states_org_fingerprint"),
    )
    op.create_index("ix_finding_states_org_host", "finding_states", ["organization_id", "host"])
    _backfill(op.get_bind())


def _backfill(bind: sa.engine.Connection) -> None:
    """Give existing findings a fingerprint and rebuild states from completed scan history."""
    meta = sa.MetaData()
    scans = sa.Table("scans", meta, autoload_with=bind)
    findings = sa.Table("findings", meta, autoload_with=bind)
    states = sa.Table("finding_states", meta, autoload_with=bind)

    rows = bind.execute(
        sa.select(scans.c.id, scans.c.organization_id, scans.c.host, scans.c.created_at, scans.c.finished_at)
        .where(scans.c.status == "completed", scans.c.organization_id.is_not(None))
        .order_by(scans.c.created_at, scans.c.id)
    ).all()
    # (organization, host) -> {fingerprint: [finding_id, first_seen, last_seen]} and the latest scan's set
    history: dict[tuple[str, str], dict[str, list[object]]] = {}
    latest: dict[tuple[str, str], set[str]] = {}
    for scan_id, org, host, created_at, finished_at in rows:
        seen_at = finished_at or created_at
        current: set[str] = set()
        for row_id, finding_id in bind.execute(
            sa.select(findings.c.row_id, findings.c.finding_id).where(findings.c.scan_id == scan_id)
        ):
            fp = _fingerprint(host, finding_id)
            bind.execute(
                findings.update()
                .where(findings.c.row_id == row_id)
                .values(
                    fingerprint=fp,
                    confidence="medium" if finding_id in HEURISTIC_IDS else "high",
                )
            )
            entry = history.setdefault((org, host), {}).setdefault(fp, [finding_id, seen_at, seen_at])
            entry[2] = seen_at
            current.add(fp)
        latest[(org, host)] = current

    now = datetime.now(UTC)
    for (org, host), known in history.items():
        for fp, (finding_id, first, last) in known.items():
            open_now = fp in latest[(org, host)]
            bind.execute(
                states.insert().values(
                    organization_id=org,
                    host=host,
                    fingerprint=fp,
                    finding_id=finding_id,
                    status="open" if open_now else "resolved",
                    first_seen_at=first,
                    last_seen_at=last,
                    resolved_at=None if open_now else last,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    op.drop_index("ix_finding_states_org_host", table_name="finding_states")
    op.drop_table("finding_states")
    op.drop_column("findings", "fingerprint")
    op.drop_column("findings", "confidence")
