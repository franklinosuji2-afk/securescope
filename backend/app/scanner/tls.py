"""TLS connection assessment with Python's standard library.

What this is: ONE verified TLS connection to the address the fetcher already validated (SSRF checks and IP
pinning happen before we get here), made with Python's default trust store and host name checking. From
that single connection we record the certificate validity dates, the issuer, the negotiated protocol
version and the negotiated cipher suite.

What this is not: a comprehensive TLS test. We do not probe other protocol versions or cipher suites,
check revocation, or test the server configuration beyond the one handshake. Python's default client
context refuses protocols older than TLS 1.2, so a server that only offers older protocols shows up as a
connection failure here, not as a graded finding.

Certificate verification is never disabled. A verification failure is classified and reported as such.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Outcome = Literal["ok", "verification_failed", "unreachable", "error"]

# OpenSSL X509_V_ERR_* codes (https://docs.openssl.org/master/man1/openssl-verification-options/).
_NOT_YET_VALID = 9
_EXPIRED = 10
_SELF_SIGNED_LEAF = 18
_SELF_SIGNED_IN_CHAIN = 19
_UNKNOWN_ISSUER = 20
_UNVERIFIABLE_LEAF = 21
_HOSTNAME_MISMATCH = 62

FailureKind = Literal["expired", "not_yet_valid", "hostname_mismatch", "untrusted", "other"]


def classify_verification_failure(code: int) -> tuple[FailureKind, str]:
    """A verification error code mapped to a kind and a message that is safe to show."""
    if code == _EXPIRED:
        return "expired", "The TLS certificate has expired."
    if code == _NOT_YET_VALID:
        return "not_yet_valid", "The TLS certificate is not valid yet."
    if code == _HOSTNAME_MISMATCH:
        return "hostname_mismatch", "The TLS certificate was issued for a different host name."
    if code in (_SELF_SIGNED_LEAF, _SELF_SIGNED_IN_CHAIN, _UNKNOWN_ISSUER, _UNVERIFIABLE_LEAF):
        return "untrusted", "The TLS certificate is self-signed or was issued by an untrusted authority."
    return "other", "The TLS certificate could not be verified."


def find_verification_error(exc: BaseException) -> ssl.SSLCertVerificationError | None:
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 10:
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        current = current.__cause__ or current.__context__
        seen += 1
    return None


@dataclass(frozen=True)
class TlsObservation:
    outcome: Outcome
    protocol: str | None = None
    cipher: str | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    issuer: str | None = None
    subject: str | None = None
    failure_kind: FailureKind | None = None
    detail: str | None = None

    def days_remaining(self, now: datetime | None = None) -> int | None:
        if self.not_after is None:
            return None
        delta = self.not_after - (now or datetime.now(UTC))
        return delta.days


def _name(rdns: object) -> str | None:
    """A readable organisation or common name from the tuple-of-tuples form getpeercert() uses."""
    wanted: dict[str, str] = {}
    if isinstance(rdns, tuple):
        for rdn in rdns:
            for item in rdn:
                if isinstance(item, tuple) and len(item) == 2:
                    wanted[str(item[0])] = str(item[1])
    value = wanted.get("organizationName") or wanted.get("commonName")
    return value[:120] if value else None


def _when(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(value), UTC)
    except (ValueError, OverflowError):
        return None


def probe_tls(
    host: str,
    address: str,
    port: int,
    timeout: float,
    context: ssl.SSLContext | None = None,
) -> TlsObservation:
    """Blocking. Connects to `address` (already validated) and verifies the certificate for `host`.

    `context` is a test seam; production leaves it None, which means the default trust store and
    host name verification.
    """
    ctx = context or ssl.create_default_context()
    try:
        with (
            socket.create_connection((address, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert() or {}
            cipher = tls.cipher()
            return TlsObservation(
                outcome="ok",
                protocol=tls.version(),
                cipher=cipher[0] if cipher else None,
                not_before=_when(cert.get("notBefore")),
                not_after=_when(cert.get("notAfter")),
                issuer=_name(cert.get("issuer")),
                subject=_name(cert.get("subject")),
            )
    except ssl.SSLCertVerificationError as exc:
        kind, message = classify_verification_failure(getattr(exc, "verify_code", 0))
        return TlsObservation(outcome="verification_failed", failure_kind=kind, detail=message)
    except ssl.SSLError:
        return TlsObservation(
            outcome="error", detail="The TLS handshake failed (for example no shared protocol or cipher)."
        )
    except TimeoutError:
        return TlsObservation(outcome="unreachable", detail="The TLS connection timed out.")
    except OSError:
        return TlsObservation(outcome="unreachable", detail="The TLS connection could not be opened.")
