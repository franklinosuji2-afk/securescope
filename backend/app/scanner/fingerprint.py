"""Stable identity for a finding on a host, so the same issue is recognised across scans."""

from __future__ import annotations

import hashlib


def fingerprint(host: str, finding_id: str) -> str:
    """Host and check id only: evidence text can change between scans without it being a new issue."""
    return hashlib.sha256(f"{host.lower()}|{finding_id}".encode()).hexdigest()[:32]
