"""App Scanning run states and the accounting rule (decision D1)."""

from __future__ import annotations

from enum import StrEnum


class AppScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    # Every selected check ran. Findings, if any, do not change this: finding something is a success.
    COMPLETED = "completed"
    # Some checks ran and some could not (for example a data source was unavailable). Never shown as clean.
    INCOMPLETE = "incomplete"
    # A scanner or the service failed. The customer is not charged.
    FAILED = "failed"
    # The service stopped while the run was in progress. The customer is not charged.
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


ACTIVE = (AppScanStatus.QUEUED.value, AppScanStatus.RUNNING.value)
FINAL = tuple(s.value for s in AppScanStatus if s.value not in ACTIVE)

# D1: one accepted run is one use. Infrastructure and scanner failures do not consume a run.
NOT_COUNTED = (AppScanStatus.FAILED.value, AppScanStatus.INTERRUPTED.value)

KINDS = ("dependency", "secrets", "sast")
