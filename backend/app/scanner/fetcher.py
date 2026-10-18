"""Safe, bounded HTTP fetching.

Safety properties implemented here:
* every hop (initial request and each redirect) is validated again, including DNS;
* the connection is pinned to the validated IP address (TLS SNI and certificate checks still
  use the original host name), which closes the DNS rebinding window between check and use;
* redirects are limited and are only followed within the same site (same host, www/non-www
  swap, or http to https upgrade); anything else is reported and not followed;
* the number of requests, timeout and response size are bounded; only GET is used;
* the response body is read up to a cap, inspected in memory and never stored.
"""

from __future__ import annotations

import ipaddress
import ssl
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings
from app.security.target import TargetError, ValidatedTarget, validate_target

USER_AGENT = "SecureScope/0.1 (+passive security posture check; authorized targets only)"


class FetchError(Exception):
    """A scan-level failure with a message that is safe to show to users."""


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    headers: httpx.Headers
    body_sample: bytes
    redirect_chain: list[str] = field(default_factory=list)
    resolved_addresses: list[str] = field(default_factory=list)
    off_origin_redirect: str | None = None
    elapsed_ms: int = 0
    requests_made: int = 0
    started_scheme: str = "https"
    final_scheme: str = "https"
    host: str = ""


def _site_key(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _is_same_site(current: ValidatedTarget, scheme: str, host: str) -> bool:
    if _site_key(host) != _site_key(current.host):
        return False
    # Never downgrade from https to http.
    return not (current.scheme == "https" and scheme == "http")


def _pinned_url(target: ValidatedTarget, address: str) -> str:
    ip = ipaddress.ip_address(address)
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    return f"{target.scheme}://{host}:{target.port}{target.path_and_query}"


def _is_tls_failure(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    return False


async def _read_capped(response: httpx.Response, limit: int) -> bytes:
    if response.is_stream_consumed:  # body already in memory (e.g. in-process test transports)
        return response.content[:limit]
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_raw():
        remaining = limit - size
        if remaining <= 0:
            break
        chunks.append(chunk[:remaining])
        size += len(chunks[-1])
        if size >= limit:
            break
    return b"".join(chunks)


async def fetch_target(
    raw_url: str,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """Fetch the target safely. `transport` is a test seam; production leaves it None."""
    started = time.monotonic()
    try:
        target = await validate_target(raw_url, settings)
    except TargetError as exc:
        raise FetchError(str(exc)) from exc

    first_scheme = target.scheme
    chain: list[str] = [target.url]
    requests_made = 0
    timeout = httpx.Timeout(settings.request_timeout_seconds)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        verify=True,
        transport=transport,
        trust_env=False,  # ignore proxy environment variables: connect exactly where validated
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=0),
    ) as client:
        for hop in range(settings.max_redirects + 1):
            if requests_made >= settings.max_requests_per_scan:
                raise FetchError("The request limit for a single scan was reached.")
            address = target.addresses[0]
            headers = {
                "Host": target.host if target.port in (80, 443) else f"{target.host}:{target.port}",
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "identity",
            }
            extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
            requests_made += 1
            try:
                async with client.stream(
                    "GET", _pinned_url(target, address), headers=headers, extensions=extensions
                ) as response:
                    body = await _read_capped(response, settings.max_response_bytes)
                    status = response.status_code
                    response_headers = response.headers
            except httpx.TimeoutException as exc:
                raise FetchError("The target did not respond in time.") from exc
            except httpx.HTTPError as exc:
                if _is_tls_failure(exc):
                    raise FetchError(
                        "The TLS certificate could not be verified (expired, self-signed, "
                        "wrong host name or untrusted issuer)."
                    ) from exc
                raise FetchError("The target could not be reached.") from exc

            location = response_headers.get("location")
            if status in (301, 302, 303, 307, 308) and location:
                if hop >= settings.max_redirects:
                    raise FetchError("Too many redirects.")
                next_url = urljoin(target.url, location)
                parts = urlsplit(next_url)
                next_host = (parts.hostname or "").lower().rstrip(".")
                next_scheme = parts.scheme.lower()
                if next_scheme not in ("http", "https") or not next_host:
                    raise FetchError("The target redirected to an unsupported location.")
                if not _is_same_site(target, next_scheme, next_host):
                    # Not followed: the redirect target is a different site.
                    return FetchResult(
                        requested_url=chain[0],
                        final_url=target.url,
                        status_code=status,
                        headers=response_headers,
                        body_sample=body,
                        redirect_chain=chain,
                        resolved_addresses=list(target.addresses),
                        off_origin_redirect=f"{next_scheme}://{next_host}",
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        requests_made=requests_made,
                        started_scheme=first_scheme,
                        final_scheme=target.scheme,
                        host=target.host,
                    )
                try:
                    target = await validate_target(next_url, settings)
                except TargetError as exc:
                    raise FetchError(f"Redirect blocked: {exc}") from exc
                chain.append(target.url)
                continue

            return FetchResult(
                requested_url=chain[0],
                final_url=target.url,
                status_code=status,
                headers=response_headers,
                body_sample=body,
                redirect_chain=chain,
                resolved_addresses=list(target.addresses),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                requests_made=requests_made,
                started_scheme=first_scheme,
                final_scheme=target.scheme,
                host=target.host,
            )
    raise FetchError("Too many redirects.")
