# Data retention

**Stored per account:** email address, a salted hash of the password (or none, for accounts that only use Google or GitHub), whether the email is confirmed, workspace memberships, and the audit log of what happened in a workspace.

**Stored per scan:** id, target URL and host, timestamps, status, score/grade, finding metadata (id, title, severity, description, redacted evidence, remediation), target metadata (final URL, resolved addresses, status code, content type, redirect chain, timing).

**Stored per report:** the first time someone downloads the PDF of a finished scan, the file is made and kept in the database (table `reports`, one per scan) with its checksum. It is only ever served through the signed-in API, never from a public address.

**Not stored:** response bodies, cookie values, credentials, or a second copy of a report outside the database.

**Retention:** scans older than the workspace's plan window (Free 30 days, Professional 90, Agency 365; see `PLANS.md`) are deleted by a background job at start-up and periodically, **together with their reports**. Deleting a scan deletes its report. Scans interrupted by a restart are marked failed. Used, revoked and expired invitations are deleted a month after they expire.

**Verification challenges:** the random value a person publishes to prove they control a domain is kept only while it can be used. It is erased as soon as the domain is verified, when the person removes it, and by the periodic background job once its 7 days have passed. After that only the fact that the domain was verified (when, and by which method) remains.

**Webhook retries:** an alert that could not be delivered is kept (host, score, and the titles of new findings, the same facts as the message) until it is delivered, has been tried five times in all, the address is switched off or deleted, or a day has passed. Then it is deleted.

**Deletion on demand:** under **Account** a person can delete their own account (password and the word DELETE required). A workspace nobody else belongs to is erased with everything in it: sites, scans, findings, reports, invitations and its audit log. In a shared workspace only that person's membership goes; what they did there stays but no longer points at them. A person who is the only owner of a workspace other people still use must hand over ownership first. Deletion is immediate and cannot be undone; the audit event `account.deleted` is written without the email address.

**Backups:** a backup taken before a deletion still contains the data until that backup is replaced (see `docs/OPERATIONS.md`).

This document is not legal advice.
