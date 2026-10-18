"""Targets and domain-ownership verification."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.models.account import AuditEventRow
from app.scanner.fetcher import FetchResult
from app.security import ownership
from app.security.target import TargetError, normalize_hostname
from app.tests.conftest import signup, trust_host

API = "/api/v1"
STRICT = Settings(database_url="sqlite://")


# --- hostname normalisation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("  Example.COM. ", "example.com"),
        ("https://Sub.Example.com:8443/path?q=1", "sub.example.com"),
        ("bücher.example", "xn--bcher-kva.example"),
    ],
)
def test_normalize_accepts_and_canonicalises(raw: str, expected: str) -> None:
    assert normalize_hostname(raw, STRICT) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "localhost",
        "intranet",
        "printer.local",
        "db.internal",
        "app.localhost",
        "10.0.0.1",
        "127.0.0.1",
        "[::1]",
        "2001:db8::1",
        "https://user:pass@example.com",
        "example.com/path",
        "example.com:8080",
        "user@example.com",
        "exa mple.com",
        "-bad.example.com",
        "bad-.example.com",
        "a..b.com",
        "exa_mple.com",
        "example.123",
        "x" * 64 + ".com",
        ("a" * 60 + ".") * 5 + "com",
        "file:///etc/passwd",
    ],
)
def test_normalize_rejects_unsafe_or_unprovable_hosts(raw: str) -> None:
    with pytest.raises(TargetError):
        normalize_hostname(raw, STRICT)


# --- CRUD, authorization, isolation -----------------------------------------------------


def create(client: TestClient, host: str = "example.com", **kw: Any) -> Any:
    return client.post(f"{API}/targets", json={"hostname": host}, **kw)


def test_create_list_get_delete(strict_client: TestClient) -> None:
    response = create(strict_client, "Example.com")
    assert response.status_code == 201, response.text
    target = response.json()
    assert target["hostname"] == "example.com"
    assert target["status"] == "pending"
    assert target["dns_record_name"] == "_securescope-challenge.example.com"
    assert target["dns_record_value"] == f"securescope-verification={target['challenge_token']}"
    assert target["http_file_url"] == "https://example.com/.well-known/securescope-verification.txt"
    assert len(target["challenge_token"]) == 32

    assert [t["id"] for t in strict_client.get(f"{API}/targets").json()["items"]] == [target["id"]]
    assert strict_client.get(f"{API}/targets/{target['id']}").json()["hostname"] == "example.com"
    assert strict_client.delete(f"{API}/targets/{target['id']}").status_code == 204
    assert strict_client.get(f"{API}/targets/{target['id']}").status_code == 404
    assert strict_client.delete(f"{API}/targets/{target['id']}").status_code == 404


def test_duplicate_and_invalid_hosts(strict_client: TestClient) -> None:
    assert create(strict_client).status_code == 201
    assert create(strict_client, "EXAMPLE.com.").status_code == 409
    for bad in ("10.0.0.1", "localhost", "example.com/x", "https://u:p@example.com"):
        assert create(strict_client, bad).status_code == 400, bad
    assert strict_client.post(f"{API}/targets", json={}).status_code == 422


def test_requires_authentication_and_csrf(anon_client: TestClient, strict_client: TestClient) -> None:
    assert anon_client.get(f"{API}/targets").status_code == 401
    assert create(anon_client).status_code == 401
    token = strict_client.headers.pop("X-CSRF-Token")
    assert create(strict_client).status_code == 403
    strict_client.headers["X-CSRF-Token"] = token


def other_org_user(client: TestClient, email: str = "bob@example.com") -> TestClient:
    other = TestClient(client.app)
    signup(other, email, f"{email} org")
    return other


def test_other_organizations_cannot_see_or_touch_a_target(strict_client: TestClient) -> None:
    target_id = create(strict_client).json()["id"]
    bob = other_org_user(strict_client)
    assert bob.get(f"{API}/targets").json()["items"] == []
    assert bob.get(f"{API}/targets/{target_id}").status_code == 404
    assert bob.delete(f"{API}/targets/{target_id}").status_code == 404
    assert bob.post(f"{API}/targets/{target_id}/challenge").status_code == 404
    verify = bob.post(f"{API}/targets/{target_id}/verify", json={"method": "dns_txt"})
    assert verify.status_code == 404
    # Bob may register the same domain for his own organization; it is independent.
    assert create(bob).status_code == 201
    assert strict_client.get(f"{API}/targets/{target_id}").json()["status"] == "pending"
    # Header spoofing does not grant access either.
    org = strict_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    assert bob.get(f"{API}/targets", headers={"X-Organization-Id": org}).status_code == 403


@pytest.mark.parametrize(
    ("role", "can_manage"),
    [("OWNER", True), ("ADMIN", True), ("SECURITY_ANALYST", True), ("MEMBER", False), ("VIEWER", False)],
)
def test_role_matrix_for_targets(strict_client: TestClient, role: str, can_manage: bool) -> None:
    org = strict_client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    existing = create(strict_client).json()["id"]
    user = other_org_user(strict_client, f"{role.lower()}@example.com")
    if role != "OWNER":
        added = strict_client.post(
            f"{API}/organizations/{org}/members", json={"email": f"{role.lower()}@example.com", "role": role}
        )
        assert added.status_code == 201, added.text
    headers = {"X-Organization-Id": org}
    if role == "OWNER":  # a second owner is added the same way
        strict_client.post(
            f"{API}/organizations/{org}/members", json={"email": "owner@example.com", "role": "OWNER"}
        )
    assert user.get(f"{API}/targets", headers=headers).status_code == 200  # every role may read
    created = create(user, "managed.example.org", headers=headers)
    assert (created.status_code == 201) is can_manage, created.text
    verify = user.post(f"{API}/targets/{existing}/verify", json={"method": "dns_txt"}, headers=headers)
    assert (verify.status_code != 403) is can_manage
    delete = user.delete(f"{API}/targets/{existing}", headers=headers)
    assert (delete.status_code == 204) is can_manage


# --- DNS TXT verification ---------------------------------------------------------------


def set_dns(client: TestClient, records: dict[str, list[str]] | Exception) -> list[str]:
    asked: list[str] = []

    async def lookup(name: str) -> list[str]:
        asked.append(name)
        if isinstance(records, Exception):
            raise records
        return records.get(name, [])

    client.app.state.s.txt_lookup = lookup  # type: ignore[attr-defined]
    return asked


def verify(client: TestClient, target_id: str, method: str = "dns_txt") -> Any:
    return client.post(f"{API}/targets/{target_id}/verify", json={"method": method})


def test_dns_txt_verification_succeeds_only_with_the_exact_challenge(strict_client: TestClient) -> None:
    target = create(strict_client).json()
    name, value = target["dns_record_name"], target["dns_record_value"]

    asked = set_dns(strict_client, {})
    body = verify(strict_client, target["id"]).json()
    assert asked == [name]  # the challenge label is queried, not the apex
    assert body["status"] == "pending" and "No TXT record" in body["last_check_error"]

    set_dns(strict_client, {name: ["securescope-verification=" + "0" * 32]})
    assert "does not match" in verify(strict_client, target["id"]).json()["last_check_error"]

    # Records on the apex or a different label must not count.
    set_dns(strict_client, {"example.com": [value], "_other.example.com": [value]})
    assert verify(strict_client, target["id"]).json()["status"] == "pending"

    set_dns(strict_client, {name: ["v=spf1 -all", f" {value} "]})
    done = verify(strict_client, target["id"]).json()
    assert done["status"] == "verified"
    assert done["verification_method"] == "dns_txt"
    assert done["verified_at"] and done["last_check_error"] is None


def test_dns_lookup_failure_is_reported_not_fatal(strict_client: TestClient) -> None:
    target = create(strict_client).json()
    set_dns(strict_client, ownership.OwnershipCheckError("The DNS lookup failed or timed out."))
    response = verify(strict_client, target["id"])
    assert response.status_code == 200
    assert response.json()["status"] == "pending" and "timed out" in response.json()["last_check_error"]


def test_verified_targets_stay_verified_and_skip_rechecks(strict_client: TestClient) -> None:
    target = create(strict_client).json()
    set_dns(strict_client, {target["dns_record_name"]: [target["dns_record_value"]]})
    assert verify(strict_client, target["id"]).json()["status"] == "verified"
    asked = set_dns(strict_client, {})
    assert verify(strict_client, target["id"]).json()["status"] == "verified"
    assert asked == []


def test_challenge_regeneration_invalidates_the_old_token(strict_client: TestClient) -> None:
    target = create(strict_client).json()
    old_value = target["dns_record_value"]
    renewed = strict_client.post(f"{API}/targets/{target['id']}/challenge").json()
    assert renewed["challenge_token"] != target["challenge_token"]
    set_dns(strict_client, {target["dns_record_name"]: [old_value]})
    assert verify(strict_client, target["id"]).json()["status"] == "pending"
    set_dns(strict_client, {target["dns_record_name"]: [renewed["dns_record_value"]]})
    assert verify(strict_client, target["id"]).json()["status"] == "verified"


def test_expired_challenges_cannot_be_used(
    strict_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.repositories.targets.CHALLENGE_TTL", timedelta(seconds=-1))
    target = create(strict_client).json()
    assert target["status"] == "expired"
    asked = set_dns(strict_client, {target["dns_record_name"]: [target["dns_record_value"]]})
    response = verify(strict_client, target["id"])
    assert response.status_code == 409 and asked == []
    monkeypatch.undo()
    assert strict_client.post(f"{API}/targets/{target['id']}/challenge").json()["status"] == "pending"


def test_verification_attempts_are_rate_limited(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    settings = make_settings(target_verifications_per_target_per_hour=2)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        target = create(client).json()
        set_dns(client, {})
        codes = [verify(client, target["id"]).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- HTTP file verification -------------------------------------------------------------


def set_http(client: TestClient, handler: Any) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[no-any-return]

    client.app.state.s.verification_transport = httpx.MockTransport(wrapped)  # type: ignore[attr-defined]
    return seen


def test_http_file_verification(local_client: TestClient) -> None:
    target = create(local_client, "localhost").json()
    content = target["http_file_content"]

    seen = set_http(local_client, lambda r: httpx.Response(200, text=content + "\n"))
    done = verify(local_client, target["id"], "http_file").json()
    assert done["status"] == "verified" and done["verification_method"] == "http_file"
    assert seen[0].url.path == "/.well-known/securescope-verification.txt"
    assert seen[0].headers["host"] == "localhost"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404, text="nope"), "HTTP 404"),
        (httpx.Response(200, text="securescope-verification=" + "f" * 32), "does not match"),
        (httpx.Response(200, text="x" * 5000), "does not match"),
        (httpx.Response(200, text=""), "does not match"),
        (httpx.Response(302, headers={"location": "https://evil.example/f.txt"}), "HTTP 302"),
    ],
)
def test_http_file_verification_failures(
    local_client: TestClient, response: httpx.Response, message: str
) -> None:
    target = create(local_client, "localhost").json()
    set_http(local_client, lambda r: response)
    body = verify(local_client, target["id"], "http_file").json()
    assert body["status"] == "pending"
    assert message in body["last_check_error"]


def test_http_file_served_from_a_different_host_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    async def fake_fetch(url: str, settings: Settings, transport: Any = None) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url="https://www.example.com/.well-known/securescope-verification.txt",
            status_code=200,
            headers=httpx.Headers(),
            body_sample=b"securescope-verification=abc",
            host="www.example.com",
        )

    monkeypatch.setattr(ownership, "fetch_target", fake_fetch)
    error = asyncio.run(ownership.verify_http_file("example.com", "abc", STRICT))
    assert error is not None and "www.example.com" in error


def test_http_verification_uses_the_ssrf_protected_fetcher(strict_client: TestClient) -> None:
    """With production settings a name resolving to a private address is refused, not fetched."""
    target = create(strict_client, "example.com").json()
    seen = set_http(strict_client, lambda r: httpx.Response(200, text=target["http_file_content"]))
    strict_client.app.state.s.settings.allow_private_targets = False  # type: ignore[attr-defined]

    async def private_resolver(host: str, port: int) -> list[Any]:
        import ipaddress

        return [ipaddress.ip_address("169.254.169.254")]

    import app.security.target as target_module

    original = target_module.resolve_host
    target_module.resolve_host = private_resolver
    try:
        body = verify(strict_client, target["id"], "http_file").json()
    finally:
        target_module.resolve_host = original
    assert body["status"] == "pending"
    assert "private" in body["last_check_error"].lower()
    assert seen == []  # no request was ever sent


# --- scans require a verified target -----------------------------------------------------


def scan(client: TestClient, url: str, **kw: Any) -> Any:
    return client.post(f"{API}/scans", json={"url": url, "authorization_confirmed": True}, **kw)


def test_scans_require_a_verified_target(local_client: TestClient, mock_server: str) -> None:
    port = mock_server.rsplit(":", 1)[1]
    refused = scan(local_client, f"http://localhost:{port}/plain")
    assert refused.status_code == 403 and "not been verified" in refused.json()["detail"]

    pending = create(local_client, "localhost").json()
    assert scan(local_client, f"http://localhost:{port}/plain").status_code == 403  # registered, unverified

    set_dns(local_client, {pending["dns_record_name"]: [pending["dns_record_value"]]})
    assert verify(local_client, pending["id"]).json()["status"] == "verified"
    assert scan(local_client, f"http://localhost:{port}/plain").status_code == 202

    local_client.delete(f"{API}/targets/{pending['id']}")
    assert scan(local_client, f"http://localhost:{port}/plain").status_code == 403


def test_verification_is_exact_host_and_per_organization(local_client: TestClient, mock_server: str) -> None:
    # alice verified 127.0.0.1 (fixture). bob, in another organization, did not.
    bob = other_org_user(local_client)
    assert scan(local_client, f"{mock_server}/plain").status_code == 202
    assert scan(bob, f"{mock_server}/plain").status_code == 403
    # A different spelling of the same machine is a different host and is not covered.
    port = mock_server.rsplit(":", 1)[1]
    assert scan(local_client, f"http://localhost:{port}/plain").status_code == 403


def test_target_lifecycle_is_audited(local_client: TestClient) -> None:
    target = create(local_client, "audited.example").json()
    set_dns(local_client, {})
    verify(local_client, target["id"])
    set_dns(local_client, {target["dns_record_name"]: [target["dns_record_value"]]})
    verify(local_client, target["id"])
    local_client.delete(f"{API}/targets/{target['id']}")
    state = local_client.app.state.s  # type: ignore[attr-defined]
    with state.audit._session() as session:
        events = [
            row.event_type
            for row in session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.resource_id == target["id"])
                .order_by(AuditEventRow.timestamp)
            )
        ]
    assert events == [
        "target.created",
        "target.verification_failed",
        "target.verified",
        "target.deleted",
    ]


def test_trust_host_helper_matches_real_verification(local_client: TestClient) -> None:
    trust_host(local_client, "helper.example")
    items = local_client.get(f"{API}/targets").json()["items"]
    assert {t["hostname"]: t["status"] for t in items}["helper.example"] == "verified"


# --- system DNS lookup error mapping ----------------------------------------------------


@pytest.mark.parametrize(
    ("raised", "expected"),
    [("NXDOMAIN", []), ("NoAnswer", []), ("Timeout", "error"), ("NoNameservers", "error")],
)
def test_system_lookup_maps_dns_errors(monkeypatch: pytest.MonkeyPatch, raised: str, expected: Any) -> None:
    import asyncio

    import dns.exception
    import dns.resolver

    exc_type: Any = {
        "NXDOMAIN": dns.resolver.NXDOMAIN,
        "NoAnswer": dns.resolver.NoAnswer,
        "Timeout": dns.exception.Timeout,
        "NoNameservers": dns.resolver.NoNameservers,
    }[raised]

    async def boom(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise exc_type()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", boom)
    if expected == "error":
        with pytest.raises(ownership.OwnershipCheckError):
            asyncio.run(ownership.system_txt_lookup("_x.example.com"))
    else:
        assert asyncio.run(ownership.system_txt_lookup("_x.example.com")) == expected
