from __future__ import annotations

import ipaddress

import pytest

from app.core.config import Settings
from app.security import target as target_module
from app.security.target import TargetError, is_public_address, parse_target_url, validate_target

pytestmark = pytest.mark.anyio

SETTINGS = Settings()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com",
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://user:pass@example.com/",
        "http://user@example.com/",
        "http:///nohost",
        "http://exa mple.com/",
        "http://localhost/",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://printer.local/",
        "http://db.internal/",
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://example.com:22/",
        "http://example.com:6379/",
        "https://example.com:3306/",
        "http://example.com:99999/",
    ],
)
def test_rejects_unsafe_syntax(url: str) -> None:
    with pytest.raises(TargetError):
        parse_target_url(url, SETTINGS)


@pytest.mark.parametrize(
    "url,expected_port",
    [
        ("http://example.com", 80),
        ("https://example.com/path?x=1", 443),
        ("https://example.com:8443/", 8443),
        ("http://93.184.216.34/", 80),
        ("https://[2606:4700:4700::1111]/", 443),
    ],
)
def test_accepts_public_syntax(url: str, expected_port: int) -> None:
    _, _, port, _ = parse_target_url(url, SETTINGS)
    assert port == expected_port


@pytest.mark.parametrize(
    "address,public",
    [
        ("93.184.216.34", True),
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.20.0.1", False),
        ("192.168.0.1", False),
        ("169.254.1.1", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("255.255.255.255", False),
        ("::1", False),
        ("::", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:10.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("2002:7f00:1::", False),
        ("2001:0:4136:e378:8000:63bf:3fff:fdd2", False),
    ],
)
def test_is_public_address(address: str, public: bool) -> None:
    assert is_public_address(ipaddress.ip_address(address)) is public


async def test_decimal_ip_literal_is_rejected() -> None:
    # 2130706433 == 127.0.0.1; the resolver normalizes it, so the resolved check catches it.
    with pytest.raises(TargetError):
        await validate_target("http://2130706433/", SETTINGS)


async def test_dns_pointing_to_private_address_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str, port: int):  # type: ignore[no-untyped-def]
        return [ipaddress.ip_address("10.0.0.7")]

    monkeypatch.setattr(target_module, "resolve_host", fake_resolve)
    with pytest.raises(TargetError, match="resolves to a private"):
        await validate_target("http://innocent.example/", SETTINGS)


async def test_mixed_public_and_private_resolution_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str, port: int):  # type: ignore[no-untyped-def]
        return [ipaddress.ip_address("93.184.216.34"), ipaddress.ip_address("127.0.0.1")]

    monkeypatch.setattr(target_module, "resolve_host", fake_resolve)
    with pytest.raises(TargetError):
        await validate_target("http://mixed.example/", SETTINGS)


async def test_public_resolution_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str, port: int):  # type: ignore[no-untyped-def]
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(target_module, "resolve_host", fake_resolve)
    result = await validate_target("https://Example.COM/a?b=1", SETTINGS)
    assert result.host == "example.com"
    assert result.url == "https://example.com/a?b=1"
    assert result.addresses == ("93.184.216.34",)


async def test_unresolvable_host_gives_clear_error() -> None:
    with pytest.raises(TargetError, match="could not be resolved"):
        await validate_target("http://definitely-not-real.invalid/", SETTINGS)


def test_the_private_target_test_switch_cannot_be_turned_on_in_a_deployed_setup() -> None:
    from app.core.config import Settings

    with pytest.raises(ValueError, match="local tests only"):
        Settings(allow_private_targets=True)  # secure cookies are the default
    with pytest.raises(ValueError, match="local tests only"):
        Settings(
            allow_private_targets=True, cookie_secure=False, public_base_url="https://getsecurescope.com"
        )
    Settings(allow_private_targets=True, cookie_secure=False)  # the local test setup still works
