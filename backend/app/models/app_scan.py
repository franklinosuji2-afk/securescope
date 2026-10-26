"""App Scanning tables: projects and the runs made against them. Separate from website scanning (`scans`).

A run stores names, sizes and digests of what was examined, never file contents. Findings tables arrive with the
parsers that produce them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AppProjectRow(Base):
    __tablename__ = "app_projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    # How results arrive: "upload" (browser) or "ci" (a customer's pipeline).
    source: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_app_projects_organization_id_name"),
        Index("ix_app_projects_organization_id", "organization_id"),
    )


class AppScanRow(Base):
    __tablename__ = "app_scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(ForeignKey("app_projects.id", ondelete="CASCADE"))
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # queued, running, completed, incomplete, failed, interrupted, cancelled (see AppScanStatus).
    status: Mapped[str] = mapped_column(String(16))
    # JSON text lists: which checks were requested, ran, and were skipped (with a fixed reason).
    kinds_json: Mapped[str] = mapped_column(Text)
    checks_run_json: Mapped[str | None] = mapped_column(Text)
    checks_skipped_json: Mapped[str | None] = mapped_column(Text)
    # Names, sizes and sha256 digests of the inputs. Never their contents.
    inputs_json: Mapped[str | None] = mapped_column(Text)
    # Tool names, versions and data timestamps that produced the result.
    scanners_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    ref: Mapped[str | None] = mapped_column(String(120))
    # The same key in one workspace never makes two runs, so a retry is never charged twice.
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    # The CI token that submitted this run, if any (for the per-token hourly limit).
    token_id: Mapped[str | None] = mapped_column(ForeignKey("api_tokens.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_app_scans_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_app_scans_token_id_created_at", "token_id", "created_at"),
        Index("ix_app_scans_project_id_created_at", "project_id", "created_at"),
        Index(
            "uq_app_scans_organization_id_idempotency_key", "organization_id", "idempotency_key", unique=True
        ),
    )


class AppFindingRow(Base):
    """One finding of one run. Evidence is stored only after redaction; file contents are never stored."""

    __tablename__ = "app_findings"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("app_scans.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    # "dependency", "secrets" or "sast".
    kind: Mapped[str] = mapped_column(String(16))
    # Advisory id (for example GHSA-... or CVE-...) or the scanner's rule id.
    rule_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(8))
    category: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    remediation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    # Where it was found: a file name and, where known, a line.
    path: Mapped[str | None] = mapped_column(String(255))
    line: Mapped[int | None] = mapped_column(Integer)
    # Dependency findings.
    ecosystem: Mapped[str | None] = mapped_column(String(16))
    package_name: Mapped[str | None] = mapped_column(String(214))
    package_version: Mapped[str | None] = mapped_column(String(64))
    fixed_versions_json: Mapped[str | None] = mapped_column(Text)
    references_json: Mapped[str | None] = mapped_column(Text)
    aliases_json: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))

    __table_args__ = (Index("ix_app_findings_scan_id_position", "scan_id", "position"),)
