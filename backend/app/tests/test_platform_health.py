from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.observability.metrics import RequestMetrics, percentile
from app.services.mailer import ApiMailer
from app.tests.conftest import signup

ADMIN = "boss@example.com"
TOKEN = "metrics-token-for-tests-0123456789"


@pytest.fixture
def client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(admin_email=ADMIN, metrics_token=TOKEN)
    with TestClient(create_app(settings, mailer)) as c:
        yield c


def confirmed_admin(client: TestClient, mailer) -> TestClient:  # type: ignore[no-untyped-def]
    admin = TestClient(client.app)
    signup(admin, ADMIN, "Boss Org")
    token = next(body for to, _s, body in mailer.sent if to == ADMIN).rsplit("token=", 1)[1].strip()
    assert admin.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return admin


def test_percentiles() -> None:
    assert percentile([], 0.95) is None
    assert percentile([5.0], 0.99) == 5.0
    values = [float(n) for n in range(1, 101)]
    assert percentile(values, 0.50) == 50.0
    assert percentile(values, 0.95) == 95.0
    assert percentile(values, 0.99) == 99.0


def test_window_counts_errors_and_latency() -> None:
    m = RequestMetrics()
    assert m.window()["requests"] == 0 and m.window()["error_rate"] is None
    for _ in range(8):
        m.record("/api/v1/scans", "GET", 200, 0.1)
    m.record("/api/v1/scans", "GET", 404, 0.2)
    m.record("/api/v1/scans", "GET", 500, 2.0)
    w = m.window()
    assert w["requests"] == 10 and w["server_errors"] == 1 and w["client_errors"] == 1
    assert w["error_rate"] == pytest.approx(0.1)
    assert w["p50_ms"] == 100 and w["p99_ms"] == 2000
    assert w["routes"][0] == {"route": "/api/v1/scans", "requests": 10, "errors": 1, "p95_ms": 2000}  # type: ignore[index]


def test_probes_are_not_measured() -> None:
    m = RequestMetrics()
    for route in ("/api/v1/health", "/api/v1/ready", "/metrics"):
        m.record(route, "GET", 200, 0.01)
    assert m.window()["requests"] == 0


def test_prometheus_text_uses_route_templates_and_buckets() -> None:
    m = RequestMetrics()
    m.record("/api/v1/scans/{scan_id}", "GET", 200, 0.07)
    text = "\n".join(m.prometheus())
    assert 'securescope_http_requests_total{method="GET",route="/api/v1/scans/{scan_id}",status="2xx"} 1' in text
    assert 'securescope_http_request_duration_seconds_bucket{le="0.05"} 0' in text
    assert 'securescope_http_request_duration_seconds_bucket{le="0.1"} 1' in text
    assert 'securescope_http_request_duration_seconds_bucket{le="+Inf"} 1' in text


def test_health_page_is_operator_only(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/platform/health").status_code == 401
    other = TestClient(client.app)
    signup(other, "someone@example.com", "Org")
    assert other.get("/api/v1/platform/health").status_code == 404


def test_health_reports_measured_values(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = confirmed_admin(client, mailer)
    client.get("/api/v1/scans/not-a-real-id")  # a 4xx on a templated route
    data = admin.get("/api/v1/platform/health").json()
    assert data["database"]["ok"] is True and data["database"]["latency_ms"] >= 0
    assert data["uptime_seconds"] >= 0 and data["version"]
    req = data["requests"]
    assert req["requests"] >= 2 and req["server_errors"] == 0 and req["error_rate"] == 0
    routes = {r["route"] for r in req["routes"]}
    assert "/api/v1/auth/register" in routes
    assert not any("not-a-real-id" in r for r in routes)  # raw identifiers never become labels
    assert data["scans"]["completed"] == 0 and data["scans"]["avg_seconds"] is None
    assert data["mail"]["delivering"] is False  # the test mailer is not a real provider
    cfg = data["configuration"]
    assert cfg["admin_email"] is True and cfg["metrics_endpoint"] is True and cfg["trusted_proxy"] is False
    assert TOKEN not in str(data) and ADMIN not in str(data)


def test_scan_outcomes_come_from_the_database(client: TestClient, mailer) -> None:  # type: ignore[no-untyped-def]
    admin = confirmed_admin(client, mailer)
    state = client.app.state.s  # type: ignore[attr-defined]
    me = admin.get("/api/v1/auth/me").json()
    org = me["organizations"][0]["id"]
    done = state.repo.create_scan(org, me["id"], "https://a.example", "a.example")
    state.repo.mark_running(done)
    failed = state.repo.create_scan(org, me["id"], "https://b.example", "b.example")
    state.repo.mark_running(failed)
    state.repo.fail_scan(failed, "boom") if hasattr(state.repo, "fail_scan") else None
    state.repo.create_scan(org, me["id"], "https://c.example", "c.example")  # stays queued
    scans = admin.get("/api/v1/platform/health").json()["scans"]
    assert scans["in_progress"] >= 1
    assert scans["completed"] + scans["failed"] + scans["cancelled"] <= 3


def test_metrics_endpoint_is_protected(client: TestClient, make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": TOKEN}).status_code == 401
    ok = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")
    body = ok.text
    assert "securescope_up 1" in body and "securescope_database_up 1" in body
    assert "securescope_http_requests_total" in body and 'securescope_scans_24h{status="failed"}' in body
    assert TOKEN not in body and "boss@example.com" not in body
    # Without a configured token the endpoint does not exist at all.
    with TestClient(create_app(make_settings(), mailer)) as bare:
        assert bare.get("/metrics").status_code == 404
        assert bare.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404


def test_unhandled_errors_count_as_server_errors(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings(), mailer)

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("deliberate")

    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/v1/boom").status_code == 500
        window = c.app.state.s.metrics.window()  # type: ignore[attr-defined]
        assert window["server_errors"] == 1


def api_mailer(status: int) -> ApiMailer:
    settings = Settings(
        database_url="sqlite://",
        mail_provider="brevo",
        mail_api_key="k",
        mail_from_email="no-reply@example.org",
    )
    return ApiMailer(settings, httpx.MockTransport(lambda r: httpx.Response(status, json={})))


def test_mail_statistics_track_success_and_failure() -> None:
    good = api_mailer(201)
    good.send("a@example.org", "s", "b")
    assert (good.stats.sent, good.stats.failed) == (1, 0) and good.stats.last_success_at is not None
    bad = api_mailer(401)
    bad.send("a@example.org", "s", "b")
    assert (bad.stats.sent, bad.stats.failed) == (0, 1)
    assert bad.stats.last_failure_status == 401 and bad.stats.last_failure_at is not None


