"""More ways to point the scanner at something internal. Every one must be refused before any request is made."""

from __future__ import annotations

import ipaddress

import pytest

from app.core.config import Settings
from app.security.target import TargetError, is_public_address, validate_target

pytestmark = pytest.mark.anyio

SETTINGS = Settings()


@pytest.mark.parametrize(
    "address",
    [
        "192.0.0.1",  # IETF protocol assignments
        "198.18.0.1",  # benchmarking
        "198.51.100.7",  # documentation
        "203.0.113.9",  # documentation
        "240.0.0.1",  # reserved
        "169.254.169.254",  # cloud metadata
        "fd00:ec2::254",  # AWS IPv6 metadata
        "64:ff9b::7f00:1",  # NAT64 wrapping 127.0.0.1
        "64:ff9b::a00:1",  # NAT64 wrapping 10.0.0.1
        "64:ff9b:1::1",  # local-use NAT64
        "::127.0.0.1",  # IPv4-compatible
        "100::1",  # discard-only
        "2001:db8::1",  # documentation
        "ff02::1",  # multicast
    ],
)
def test_more_internal_addresses_are_not_public(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://0x7f000001/",  # hexadecimal 127.0.0.1
        "http://0177.0.0.1/",  # octal 127.0.0.1
        "http://127.1/",  # short form
        "http://2130706433/",  # decimal
        "http://[::ffff:7f00:1]/",  # IPv4-mapped, hex form
        "http://[64:ff9b::7f00:1]/",
        "http://localhost./",  # trailing dot
        "http://LOCALHOST/",
        "http://metadata.google.internal/",
        "http://user:pass@93.184.216.34/",  # credentials in the URL
        "http://93.184.216.34@127.0.0.1/",  # userinfo trick
        "http://example.com:22/",
        "http://example.com:2375/",
        "gopher://127.0.0.1/",
        "http://127.0.0.1\\@93.184.216.34/",
    ],
)
async def test_tricky_targets_are_refused(url: str) -> None:
    with pytest.raises(TargetError):
        await validate_target(url, SETTINGS)
