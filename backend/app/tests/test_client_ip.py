"""Which address rate limits are keyed on, and that a visitor cannot choose it."""

from __future__ import annotations

import itertools
from collections.abc import Callable

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.tests.conftest import PASSWORD, CapturingMailer

SECRET = "shared-secret-for-tests"
LOGIN = "/api/v1/auth/login"
_emails = itertools.count()


def bad_logins(client: TestClient, count: int, headers: dict[str, str]) -> list[int]:
    codes = []
    for _ in range(count):
        # A different email each time, so only the per-IP limit can stop us.
        r = client.post(
            LOGIN, json={"email": f"u{next(_emails)}@example.com", "password": PASSWORD}, headers=headers
        )
        codes.append(r.status_code)
    return codes


def client_for(
    make_settings: Callable[..., Settings], mailer: CapturingMailer, **extra: object
) -> TestClient:
    settings = make_settings(login_attempts_per_ip_per_15min=3, **extra)
    return TestClient(create_app(settings, mailer))


def test_without_a_secret_forged_headers_change_nothing(
    make_settings: Callable[..., Settings], mailer: CapturingMailer
) -> None:
    with client_for(make_settings, mailer, trusted_proxy_secret=SECRET) as client:
        forged = [{"x-real-client-ip": f"203.0.113.{i}"} for i in range(6)]
        codes = [bad_logins(client, 1, h)[0] for h in forged]
    assert codes[:3] == [401, 401, 401] and 429 in codes[3:]  # one real client, rotating fake addresses


def test_a_wrong_secret_is_ignored(make_settings: Callable[..., Settings], mailer: CapturingMailer) -> None:
    with client_for(make_settings, mailer, trusted_proxy_secret=SECRET) as client:
        codes = [
            bad_logins(client, 1, {"x-proxy-secret": "wrong", "x-real-client-ip": f"203.0.113.{i}"})[0]
            for i in range(6)
        ]
    assert 429 in codes


def test_with_the_secret_each_visitor_is_limited_separately(
    make_settings: Callable[..., Settings], mailer: CapturingMailer
) -> None:
    with client_for(make_settings, mailer, trusted_proxy_secret=SECRET) as client:
        first = {"x-proxy-secret": SECRET, "x-real-client-ip": "203.0.113.10"}
        second = {"x-proxy-secret": SECRET, "x-real-client-ip": "203.0.113.11"}
        assert bad_logins(client, 4, first)[-1] == 429
        assert bad_logins(client, 1, second) == [401]  # a different visitor is not blocked by the first


def test_a_malformed_address_falls_back_to_the_peer(
    make_settings: Callable[..., Settings], mailer: CapturingMailer
) -> None:
    with client_for(make_settings, mailer, trusted_proxy_secret=SECRET) as client:
        codes = [
            bad_logins(client, 1, {"x-proxy-secret": SECRET, "x-real-client-ip": f"not-an-ip-{i}"})[0]
            for i in range(6)
        ]
    assert 429 in codes


def test_legacy_forwarded_for_only_when_explicitly_enabled(
    make_settings: Callable[..., Settings], mailer: CapturingMailer
) -> None:
    with client_for(
        make_settings, mailer
    ) as client:  # off by default: rotating X-Forwarded-For does not help
        codes = [bad_logins(client, 1, {"x-forwarded-for": f"198.51.100.{i}"})[0] for i in range(6)]
    assert 429 in codes
    with client_for(make_settings, mailer, trust_proxy_headers=True) as client:
        codes = [bad_logins(client, 1, {"x-forwarded-for": f"198.51.100.{i}"})[0] for i in range(6)]
    assert 429 not in codes
