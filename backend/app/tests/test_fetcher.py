from __future__ import annotations

import ipaddress
import ssl

import httpx
import pytest

from app.core.config import Settings
from app.scanner.fetcher import FetchError, fetch_target
from app.security import target as target_module

pytestmark = pytest.mark.anyio

PUBLIC = ipaddress.ip_address("93.184.216.34")
OTHER_PUBLIC = ipaddress.ip_address("93.184.216.35")
SETTINGS = Settings()


def patch_dns(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, list[str]]) -> list[str]:
    calls: list[str] = []

    async def fake(host: str, port: int):  # type: ignore[no-untyped-def]
        calls.append(host)
        answers = mapping[host]
        value = answers.pop(0) if len(answers) > 1 else answers[0]
        return [ipaddress.ip_address(value)]

    monkeypatch.setattr(target_module, "resolve_host", fake)
    return calls


async def test_connection_is_pinned_to_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html/>")

    result = await fetch_target("https://site.example/x", SETTINGS, httpx.MockTransport(handler))
    request = seen[0]
    assert request.url.host == "93.184.216.34"  # connects to the validated address, not the name
    assert request.headers["host"] == "site.example"
    assert request.extensions["sni_hostname"] == "site.example"
    assert request.method == "GET"
    assert result.status_code == 200 and result.resolved_addresses == ["93.184.216.34"]


async def test_same_site_redirects_are_followed_and_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_dns(monkeypatch, {"site.example": ["93.184.216.34"], "www.site.example": ["93.184.216.35"]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "93.184.216.34":
            return httpx.Response(301, headers={"location": "https://www.site.example/home"})
        return httpx.Response(200, content=b"<html/>")

    result = await fetch_target("http://site.example/", SETTINGS, httpx.MockTransport(handler))
    assert result.final_url == "https://www.site.example/home"
    assert result.started_scheme == "http" and result.final_scheme == "https"
    assert calls == ["site.example", "www.site.example"]  # DNS validated on every hop


async def test_off_origin_redirect_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    result = await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))
    assert result.off_origin_redirect == "https://evil.example"
    assert len(requested) == 1


async def test_https_to_http_downgrade_redirect_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://site.example/"})

    result = await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))
    assert result.off_origin_redirect is not None


async def test_dns_rebinding_between_hops_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # First lookup is public; the second lookup for the same site now points at an internal address.
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34", "169.254.169.254"]})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/next"})

    with pytest.raises(FetchError, match="Redirect blocked"):
        await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))


async def test_redirect_to_private_ip_literal_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    result = await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))
    assert requested == ["93.184.216.34"]
    assert result.off_origin_redirect == "http://169.254.169.254"


async def test_redirect_loop_is_cut_off(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(FetchError, match="Too many redirects"):
        await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))
    assert count <= SETTINGS.max_redirects + 1


async def test_request_budget_per_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    small = Settings(max_requests_per_scan=2, max_redirects=10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(FetchError, match="request limit"):
        await fetch_target("https://site.example/", small, httpx.MockTransport(handler))


async def test_response_body_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})
    small = Settings(max_response_bytes=4096)
    pulled = 0

    class Endless(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            nonlocal pulled
            for _ in range(10_000):
                pulled += 1
                yield b"x" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Endless())

    result = await fetch_target("https://site.example/", small, httpx.MockTransport(handler))
    assert len(result.body_sample) == 4096
    assert pulled < 20  # stopped reading long before the 10 MB the server offered


async def test_private_start_target_is_rejected_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made")

    with pytest.raises(FetchError):
        await fetch_target("http://10.0.0.1/", SETTINGS, httpx.MockTransport(handler))


async def test_tls_failure_gets_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})

    def handler(request: httpx.Request) -> httpx.Response:
        error = httpx.ConnectError("handshake failed")
        error.__cause__ = ssl.SSLCertVerificationError("certificate verify failed")
        raise error

    with pytest.raises(FetchError, match="TLS certificate"):
        await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))


async def test_timeout_message(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dns(monkeypatch, {"site.example": ["93.184.216.34"]})

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(FetchError, match="did not respond in time"):
        await fetch_target("https://site.example/", SETTINGS, httpx.MockTransport(handler))
