"""Domain-ownership verification: DNS TXT record or a file under /.well-known/.

Both checks prove control of the host name, which is the only thing that authorises a scan.
The HTTP check goes through the same SSRF-hardened fetcher as scans (public addresses only,
DNS pinning, same-site redirects, size and time limits).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx

from app.core.config import Settings
from app.scanner.fetcher import FetchError, fetch_target

DNS_PREFIX = "_securescope-challenge"
WELL_KNOWN_PATH = "/.well-known/securescope-verification.txt"
VALUE_PREFIX = "securescope-verification="
MAX_FILE_BYTES = 512

TxtLookup = Callable[[str], Awaitable[list[str]]]


class OwnershipCheckError(Exception):
    """The check could not be completed (as opposed to completing and not matching)."""


def challenge_value(token: str) -> str:
    return f"{VALUE_PREFIX}{token}"


def dns_record_name(hostname: str) -> str:
    return f"{DNS_PREFIX}.{hostname}"


def http_file_url(hostname: str) -> str:
    return f"https://{hostname}{WELL_KNOWN_PATH}"


async def system_txt_lookup(name: str) -> list[str]:
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 5.0
    try:
        answer = await resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException as exc:
        raise OwnershipCheckError("The DNS lookup failed or timed out. Try again in a few minutes.") from exc
    return ["".join(part.decode("utf-8", "replace") for part in rdata.strings) for rdata in answer]


async def verify_dns_txt(hostname: str, token: str, lookup: TxtLookup) -> str | None:
    """Returns None on success, otherwise a user-safe reason."""
    name = dns_record_name(hostname)
    records = await lookup(name)
    if not records:
        return f"No TXT record was found at {name}. DNS changes can take a while to propagate."
    expected = challenge_value(token)
    if any(record.strip() == expected for record in records):
        return None
    return f"A TXT record exists at {name} but its value does not match the current challenge."


async def verify_http_file(
    hostname: str,
    token: str,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str | None:
    expected = challenge_value(token)
    last_error = "The verification file could not be fetched."
    for scheme in ("https", "http"):
        try:
            result = await fetch_target(f"{scheme}://{hostname}{WELL_KNOWN_PATH}", settings, transport)
        except FetchError as exc:
            last_error = str(exc)
            continue
        if result.host != hostname:
            # A redirect to www.* (or similar) proves control of a different name.
            last_error = f"The file was served from {result.host}, not {hostname}."
            continue
        if result.status_code != 200:
            last_error = f"The verification file returned HTTP {result.status_code}."
            continue
        body = result.body_sample
        if len(body) > MAX_FILE_BYTES or body.decode("utf-8", "replace").strip() != expected:
            last_error = "The verification file was found but its content does not match the challenge."
            continue
        return None
    return last_error
