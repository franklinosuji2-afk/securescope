# Data retention policy (v0.1, self-hosted)

**Stored per scan:** id, target URL and host, timestamps, status, score/grade, finding metadata (id, title, severity, description, redacted evidence, remediation), target metadata (final URL, resolved addresses, status code, content type, redirect chain, timing).

**Not stored:** response bodies, cookie values, credentials. No user accounts or contact details are collected.

**Retention:** scans older than `SECURESCOPE_RETENTION_DAYS` (default 30) are deleted by a background job at start-up and periodically. Scans interrupted by a restart are marked failed.

**Deletion on demand:** `docker compose down -v` removes the data volume.

**Before any hosted offering:** define a privacy notice, lawful basis, user-initiated deletion and processor terms. This document is not legal advice.
