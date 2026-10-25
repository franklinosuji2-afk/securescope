"""More ways to point the scanner at something internal. Every one must be refused before any request is made."""

from __future__ import annotations

import ipaddress
from typing import Any

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


EXTRA_NOT_PUBLIC = [
    "100.64.0.1",  # carrier-grade NAT
    "100.127.255.254",
    "0.0.0.0",  # noqa: S104
    "::",
    "::1",
    "::ffff:169.254.169.254",  # IPv4-mapped cloud metadata
    "::ffff:10.1.2.3",
    "fe80::1",
    "fc00::1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "255.255.255.255",
]


@pytest.mark.parametrize("address", EXTRA_NOT_PUBLIC)
def test_further_internal_addresses_are_not_public(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address)) is False


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111", "34.200.1.1"])
def test_ordinary_public_addresses_still_pass(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address)) is True


WEBHOOK_URLS = [
    "https://0x7f000001/hook",
    "https://0177.0.0.1/hook",
    "https://2130706433/hook",
    "https://127.1/hook",
    "https://[::ffff:7f00:1]/hook",
    "https://[::ffff:169.254.169.254]/hook",
    "https://100.64.0.1/hook",
    "https://0.0.0.0/hook",
    "https://localhost./hook",
    "https://LOCALHOST/hook",
    "https://metadata.google.internal/latest",
    "https://user:pass@93.184.216.34/hook",
    "https://93.184.216.34@127.0.0.1/hook",
    "https://example.com:22/hook",
    "https://example.com:6379/hook",
    "http://93.184.216.34/hook",
    "ftp://93.184.216.34/hook",
    "https://127.0.0.1\\@93.184.216.34/hook",
]


@pytest.mark.parametrize("url", WEBHOOK_URLS)
def test_a_webhook_address_cannot_name_anything_internal_and_nothing_is_stored(
    url: str, make_settings: Any, mailer: Any
) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.tests.conftest import signup

    with TestClient(create_app(make_settings(webhook_signing_key="k" * 40), mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        response = client.post("/api/v1/webhooks", json={"url": url})
        assert response.status_code in (400, 422), f"{url} -> {response.status_code}"
        assert client.get("/api/v1/webhooks").json()["items"] == []
