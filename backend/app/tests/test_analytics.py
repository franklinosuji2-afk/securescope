from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.analytics import (
    View,
    device_class,
    is_bot,
    referrer_host,
    resolve_timezone,
    summarise,
    visitor_hash,
)
from app.tests.conftest import signup

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605 Mobile/15E148"
ADMIN = "boss@example.com"


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(
        admin_email=ADMIN, analytics_salt="s" * 32, public_base_url="https://getsecurescope.com"
    )
    with TestClient(create_app(settings, mailer)) as c:
        yield c


def collect(client: TestClient, page: str = "login", ua: str = BROWSER, **extra: object) -> int:
    headers = {"User-Agent": ua, **{k: str(v) for k, v in extra.items() if k.startswith("X-")}}
    body: dict[str, object] = {"page": page}
    if "referrer" in extra:
        body["referrer"] = extra["referrer"]
    return client.post("/api/v1/analytics/collect", json=body, headers=headers).status_code


def test_classifiers() -> None:
    assert is_bot("") and is_bot("Googlebot/2.1") and is_bot("curl/8.0") and not is_bot(BROWSER)
    assert device_class(PHONE) == "mobile"
    assert device_class("Mozilla/5.0 (iPad; CPU OS 17_0)") == "tablet"
    assert device_class("Mozilla/5.0 (Linux; Android 14) Chrome/120") == "tablet"
    assert device_class(BROWSER) == "desktop"


def test_referrer_keeps_only_a_foreign_host() -> None:
    own = ["getsecurescope.com"]
    assert referrer_host("https://www.google.com/search?q=secret&x=1", own) == "www.google.com"
    assert referrer_host("https://getsecurescope.com/#/login", own) is None
    assert referrer_host("", own) is None and referrer_host(None, own) is None
    assert referrer_host("javascript:alert(1)", own) is None
    assert referrer_host("not a url", own) is None


def test_visitor_hash_changes_daily_and_hides_inputs() -> None:
    day = datetime(2026, 10, 20, tzinfo=UTC).date()
    a = visitor_hash("salt", day, "203.0.113.9", BROWSER)
    assert a == visitor_hash("salt", day, "203.0.113.9", BROWSER)
    assert a != visitor_hash("salt", day + timedelta(days=1), "203.0.113.9", BROWSER)
    assert a != visitor_hash("other", day, "203.0.113.9", BROWSER)
    assert "203.0.113.9" not in a and len(a) == 32


def test_summarise_counts_days_pages_and_comparison() -> None:
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    tz = resolve_timezone("UTC")

    def v(days_ago: int, page: str, visitor: str, ref: str | None = None, device: str = "desktop") -> View:
        return View(now - timedelta(days=days_ago, minutes=days_ago), page, ref, device, visitor)

    views = [
        v(0, "login", "a"),
        v(0, "privacy", "a"),
        v(0, "login", "b", "news.example"),
        v(1, "register", "c", device="mobile"),
        v(8, "login", "d"),  # previous 7-day period
    ]
    out = summarise(views, days=7, tz=tz, now=now)
    assert out["today"] == {"views": 3, "visitors": 2}
    assert out["yesterday"] == {"views": 1, "visitors": 1}
    assert out["current"]["views"] == 4 and out["current"]["visitors"] == 3  # type: ignore[index]
    assert out["previous"]["views"] == 1  # type: ignore[index]
    assert len(out["current"]["series"]) == 7  # type: ignore[index]
    assert out["top_pages"][0] == {"name": "login", "count": 2, "visitors": 2}  # type: ignore[index]
    # Landing = each visitor's first view of the day.
    landing = {x["name"]: x["count"] for x in out["landing_pages"]}  # type: ignore[attr-defined]
    assert landing == {"login": 2, "register": 1}
    sources = {x["name"]: x["count"] for x in out["sources"]}  # type: ignore[attr-defined]
    assert sources == {"Direct": 2, "news.example": 1}
    assert {x["name"]: x["count"] for x in out["devices"]} == {"desktop": 2, "mobile": 1}  # type: ignore[attr-defined]


def test_summarise_uses_the_viewers_time_zone() -> None:
    # 23:30 UTC on the 19th is already the 20th in Berlin (UTC+2 in October).
    now = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    late = View(datetime(2026, 10, 19, 23, 30, tzinfo=UTC), "login", None, "desktop", "x")
    assert summarise([late], days=3, tz=resolve_timezone("Europe/Berlin"), now=now)["today"]["views"] == 1  # type: ignore[index]
    assert summarise([late], days=3, tz=resolve_timezone("UTC"), now=now)["today"]["views"] == 0  # type: ignore[index]
    assert resolve_timezone("Not/AZone") is UTC


def test_collect_is_public_and_stores_no_address_or_agent(client: TestClient) -> None:
    assert collect(client, "login", referrer="https://news.example/story?id=5") == 204
    state = client.app.state.s  # type: ignore[attr-defined]
    rows = state.analytics.views_since(datetime.now(UTC) - timedelta(minutes=5))
    assert len(rows) == 1
    row = rows[0]
    assert (row.page, row.referrer_host, row.device) == ("login", "news.example", "desktop")
    dumped = repr(row)
    assert "testclient" not in dumped and "Mozilla" not in dumped and "story" not in dumped


def test_collect_rejects_unknown_pages_and_extra_fields(client: TestClient) -> None:
    assert client.post("/api/v1/analytics/collect", json={"page": "overview"}).status_code == 422
    assert client.post("/api/v1/analytics/collect", json={"page": "login", "path": "/x"}).status_code == 422
    assert (
        client.post("/api/v1/analytics/collect", json={"page": "login", "referrer": "x" * 600}).status_code
        == 422
    )


def test_collect_drops_bots_and_opt_outs_silently(client: TestClient) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    assert collect(client, ua="Googlebot/2.1") == 204
    assert collect(client, ua="") == 204
    assert (
        client.post(
            "/api/v1/analytics/collect", json={"page": "login"}, headers={"User-Agent": BROWSER, "DNT": "1"}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/analytics/collect",
            json={"page": "login"},
            headers={"User-Agent": BROWSER, "Sec-GPC": "1"},
        ).status_code
        == 204
    )
    assert state.analytics.views_since(datetime.now(UTC) - timedelta(days=1)) == []


def test_collect_is_rate_limited_per_client(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(analytics_events_per_client_per_hour=3)
    with TestClient(create_app(settings, mailer)) as c:
        for _ in range(6):
            assert collect(c) == 204
        stored = c.app.state.s.analytics.views_since(datetime.now(UTC) - timedelta(minutes=5))  # type: ignore[attr-defined]
        assert len(stored) == 3


def test_collect_can_be_switched_off(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(analytics_enabled=False), mailer)) as c:
        assert collect(c) == 204
        assert c.app.state.s.analytics.views_since(datetime.now(UTC) - timedelta(days=1)) == []  # type: ignore[attr-defined]


def test_same_visitor_same_day_is_one_visitor(client: TestClient) -> None:
    collect(client, "login")
    collect(client, "privacy")
    state = client.app.state.s  # type: ignore[attr-defined]
    rows = state.analytics.views_since(datetime.now(UTC) - timedelta(minutes=5))
    assert len(rows) == 2 and len({r.visitor for r in rows}) == 1


def test_summary_requires_the_admin(client: TestClient) -> None:
    assert client.get("/api/v1/analytics/summary").status_code == 401
    other = TestClient(client.app)
    signup(other, "someone@example.com", "Org")
    assert other.get("/api/v1/analytics/summary").status_code == 404
    assert other.get("/api/v1/auth/me").json()["is_admin"] is False


def test_unconfirmed_admin_email_is_not_admin(client: TestClient) -> None:
    admin = TestClient(client.app)
    signup(admin, ADMIN, "Boss Org")
    # Registered but the address is not confirmed yet.
    assert admin.get("/api/v1/auth/me").json()["is_admin"] is False
    assert admin.get("/api/v1/analytics/summary").status_code == 404


def confirm(client: TestClient, mailer, email: str) -> TestClient:  # type: ignore[no-untyped-def]
    admin = TestClient(client.app)
    signup(admin, email, "Boss Org")
    token = next(body for to, _s, body in mailer.sent if to == email).rsplit("token=", 1)[1].strip()
    assert admin.post("/api/v1/auth/verify-email", json={"token": token}).status_code in (200, 204)
    return admin


def test_admin_sees_the_summary(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = confirm(client, mailer, ADMIN)
    assert admin.get("/api/v1/auth/me").json()["is_admin"] is True
    empty = admin.get("/api/v1/analytics/summary?days=7&tz=Europe/Berlin").json()
    assert empty["last_event_at"] is None and empty["current"]["views"] == 0
    assert empty["timezone"] == "Europe/Berlin" and len(empty["current"]["series"]) == 7

    collect(client, "login")
    collect(client, "privacy", ua=PHONE, referrer="https://www.google.com/")
    data = admin.get("/api/v1/analytics/summary?days=7").json()
    assert data["last_event_at"] is not None and data["tracking_enabled"] is True
    assert data["today"]["views"] == 2 and data["today"]["visitors"] == 2
    assert {d["name"] for d in data["devices"]} == {"desktop", "mobile"}
    assert {s["name"] for s in data["sources"]} == {"Direct", "www.google.com"}


def test_summary_validates_its_parameters(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = confirm(client, mailer, ADMIN)
    assert admin.get("/api/v1/analytics/summary?days=0").status_code == 422
    assert admin.get("/api/v1/analytics/summary?days=500").status_code == 422
    assert admin.get("/api/v1/analytics/summary?tz=Nope/Nope").status_code == 200  # falls back to UTC


def test_retention_removes_old_views(client: TestClient) -> None:
    state = client.app.state.s  # type: ignore[attr-defined]
    old = View(datetime.now(UTC) - timedelta(days=200), "login", None, "desktop", "o")
    state.analytics.add(old)
    collect(client)
    # The start-up maintenance task may already have removed it, so assert the outcome, not who did it.
    state.analytics.delete_older_than(90)
    remaining = state.analytics.views_since(datetime.now(UTC) - timedelta(days=400))
    assert [r.visitor for r in remaining] != ["o"] and len(remaining) == 1
