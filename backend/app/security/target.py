"""Target validation: the first line of defence against SSRF and abuse.

Everything here runs server side and is applied before every outbound request,
including every redirect hop.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from app.core.config import Settings

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

MAX_URL_LENGTH = 2048
BLOCKED_HOSTNAME_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


class TargetError(ValueError):
    """Raised when a target is not allowed. The message is safe to show to users."""


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    path_and_query: str
    addresses: tuple[str, ...]

    @property
    def origin(self) -> str:
        default = 443 if self.scheme == "https" else 80
        suffix = "" if self.port == default else f":{self.port}"
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.scheme}://{host}{suffix}"


def is_public_address(address: IPAddress) -> bool:
    """True only for globally routable unicast addresses."""
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            return is_public_address(mapped)
        if address.sixtofour is not None and not is_public_address(address.sixtofour):
            return False
        if address.teredo is not None:
            return False
    return bool(address.is_global) and not (
        address.is_multicast
        or address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_reserved
        or address.is_unspecified
    )


def parse_target_url(raw: str, settings: Settings) -> tuple[str, str, int, str]:
    """Syntactic validation. Returns (scheme, host, port, path_and_query)."""
    candidate = (raw or "").strip()
    if not candidate:
        raise TargetError("A target URL is required.")
    if len(candidate) > MAX_URL_LENGTH:
        raise TargetError("The URL is too long.")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in candidate):
        raise TargetError("The URL contains whitespace or control characters.")
    if "://" not in candidate:
        raise TargetError("The URL must start with http:// or https://.")
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:
        raise TargetError("The URL is not valid.") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise TargetError("Only http:// and https:// URLs are supported.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise TargetError("URLs with embedded credentials are not allowed.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise TargetError("The URL has no host name.")
    if port is None:
        port = 443 if scheme == "https" else 80
    if not settings.allow_private_targets:
        if port not in settings.allowed_ports:
            allowed = ", ".join(str(p) for p in settings.allowed_ports)
            raise TargetError(f"Port {port} is not allowed. Allowed ports: {allowed}.")
        if host == "localhost" or host.endswith(BLOCKED_HOSTNAME_SUFFIXES):
            raise TargetError("Local and internal host names are not allowed.")
        literal = _as_ip(host)
        if literal is not None and not is_public_address(literal):
            raise TargetError("Private, loopback, link-local and reserved addresses are not allowed.")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return scheme, host, port, path


def _as_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


async def resolve_host(host: str, port: int) -> list[IPAddress]:
    """Resolve a host to addresses without trusting the result yet."""
    literal = _as_ip(host)
    if literal is not None:
        return [literal]
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise TargetError("The host name could not be resolved.") from exc
    seen: dict[str, IPAddress] = {}
    for info in infos:
        text = str(info[4][0]).split("%", 1)[0]
        parsed = _as_ip(text)
        if parsed is not None:
            seen[text] = parsed
    if not seen:
        raise TargetError("The host name did not resolve to an address.")
    return list(seen.values())


async def validate_target(raw: str, settings: Settings) -> ValidatedTarget:
    """Full validation: syntax, then DNS, then every resolved address must be public."""
    scheme, host, port, path = parse_target_url(raw, settings)
    addresses = await resolve_host(host, port)
    if not settings.allow_private_targets:
        bad = [a for a in addresses if not is_public_address(a)]
        if bad:
            # All-or-nothing: a name that resolves to any non-public address is rejected.
            raise TargetError("The host resolves to a private, loopback, link-local or reserved address.")
    target = ValidatedTarget(
        url="",
        scheme=scheme,
        host=host,
        port=port,
        path_and_query=path,
        addresses=tuple(str(a) for a in addresses),
    )
    return replace(target, url=f"{target.origin}{path}")
