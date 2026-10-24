"""Webhook alerts: safe addresses, signed messages, retries, limits and the alert itself."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.webhooks import AUTO_DISABLE_AFTER, MAX_PER_ORGANIZATION, address_of
from app.tests.conftest import CapturingMailer, signup, trust_host
from app.tests.test_schedules import CRON, SECRET, make_due, run_cron, target_id_of
from app.tests.test_tenancy import add_member, new_user, org_of

KEY = "k" * 40
HOOK = "https://127.0.0.1/hooks/abc123-secret-token"


class Receiver:
    """Stands in for the customer's server and records what arrived."""

    def __init__(self, *statuses: int) -> None:
        self.statuses = list(statuses) or [200]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.statuses) - 1)
        return httpx.Response(self.statuses[index])

    def install(self, client: TestClient) -> Receiver:
        state = client.app.state.s  # type: ignore[attr-defined]
        state.webhooks.transport = httpx.MockTransport(self)
        state.webhooks.retry_delay = 0
        return self


@pytest.fixture
def hook_client(make_settings, mailer):  # type: ignore[no-untyped-def]
    settings = make_settings(
        allow_private_targets=True, request_timeout_seconds=1.0, cron_secret=SECRET, webhook_signing_key=KEY
    )
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        trust_host(client, "127.0.0.1")
        yield client


def create(client: TestClient, url: str = HOOK) -> dict[str, Any]:
    response = client.post("/api/v1/webhooks", json={"url": url})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def verify(request: httpx.Request, secret: str) -> dict[str, Any]:
    parts = dict(p.split("=", 1) for p in request.headers["x-securescope-signature"].split(","))
    expected = hmac.new(
        secret.encode(), f"{parts['t']}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(parts["v1"], expected)
    return json.loads(request.content)  # type: ignore[no-any-return]


# --- addresses -------------------------------------------------------------------------------------------


def test_an_address_is_shown_without_its_path() -> None:
    assert address_of("https://hooks.example.com/services/T000/B000/XXXX") == "https://hooks.example.com/…"
    assert address_of("https://hooks.example.com:8443/x?token=1") == "https://hooks.example.com:8443/…"


def test_the_list_never_repeats_the_secret_part_of_an_address(hook_client: TestClient) -> None:
    Receiver().install(hook_client)
    create(hook_client)
    text = hook_client.get("/api/v1/webhooks").text
    assert "abc123-secret-token" not in text and "https://127.0.0.1/…" in text


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "ftp://example.com/hook",
        "https://user:pw@example.com/hook",
        "example.com/hook",
    ],
)
def test_only_plain_https_addresses_are_accepted(hook_client: TestClient, url: str) -> None:
    assert hook_client.post("/api/v1/webhooks", json={"url": url}).status_code == 400


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://localhost/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://10.0.0.5/hook",
        "https://[::1]/hook",
        "https://service.internal/hook",
    ],
)
def test_internal_addresses_are_refused(make_settings, mailer, url: str) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(webhook_signing_key=KEY), mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        response = client.post("/api/v1/webhooks", json={"url": url})
        assert response.status_code == 400
        assert "private" in response.text.lower() or "not allowed" in response.text.lower()


# --- the feature switch, the plan and permissions -----------------------------------------------------


def test_without_a_signing_key_the_feature_says_so(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(allow_private_targets=True), mailer)) as client:
        signup(client, "alice@example.com", "Alice Org")
        listing = client.get("/api/v1/webhooks").json()
        assert listing["configured"] is False and listing["items"] == []
        assert client.post("/api/v1/webhooks", json={"url": HOOK}).status_code == 503


def test_a_short_signing_key_is_refused_at_start_up(make_settings) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="WEBHOOK_SIGNING_KEY"):
        make_settings(webhook_signing_key="short")


def test_a_free_workspace_cannot_add_webhooks_but_can_see_why(make_settings, mailer) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(default_plan=None, allow_private_targets=True, webhook_signing_key=KEY)
    with TestClient(create_app(settings, mailer)) as client:
        signup(client, "free@example.com", "Free Org")
        assert client.get("/api/v1/webhooks").json()["available"] is False
        response = client.post("/api/v1/webhooks", json={"url": HOOK})
        assert response.status_code == 403 and "Professional and Agency" in response.json()["detail"]


def test_a_viewer_can_read_but_not_change_webhooks(hook_client: TestClient) -> None:
    org = org_of(hook_client)
    viewer = new_user(hook_client, "viewer@example.com")
    add_member(hook_client, org, "viewer@example.com", "VIEWER")
    headers = {"X-Organization-Id": org}
    assert viewer.get("/api/v1/webhooks", headers=headers).status_code == 200
    assert viewer.post("/api/v1/webhooks", json={"url": HOOK}, headers=headers).status_code == 403


def test_another_workspace_cannot_touch_my_webhook(hook_client: TestClient) -> None:
    Receiver().install(hook_client)
    mine = create(hook_client)
    other = new_user(hook_client, "mallory@example.com")
    for method, path in (
        ("delete", f"/api/v1/webhooks/{mine['id']}"),
        ("post", f"/api/v1/webhooks/{mine['id']}/test"),
        ("post", f"/api/v1/webhooks/{mine['id']}/rotate"),
    ):
        assert getattr(other, method)(path).status_code == 404
    assert other.get("/api/v1/webhooks").json()["items"] == []
    assert len(hook_client.get("/api/v1/webhooks").json()["items"]) == 1


def test_a_workspace_has_a_limit(hook_client: TestClient) -> None:
    for i in range(MAX_PER_ORGANIZATION):
        create(hook_client, f"https://127.0.0.1/hook{i}")
    assert hook_client.post("/api/v1/webhooks", json={"url": HOOK}).status_code == 409


# --- signing ---------------------------------------------------------------------------------------------


def test_the_secret_is_shown_once_and_signs_the_message(hook_client: TestClient) -> None:
    receiver = Receiver().install(hook_client)
    created = create(hook_client)
    secret = created["signing_secret"]
    assert secret.startswith("whsec_") and len(secret) > 40
    assert "signing_secret" not in hook_client.get("/api/v1/webhooks").text
    result = hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result == {"ok": True, "status": "Delivered (HTTP 200)"}
    request = receiver.requests[0]
    body = verify(request, secret)
    assert body["event"] == "webhook.test" and body["delivery_id"]
    assert request.headers["x-securescope-event"] == "webhook.test"
    assert request.headers["content-type"] == "application/json"
    assert request.url.path == "/hooks/abc123-secret-token"


def test_a_wrong_secret_does_not_verify(hook_client: TestClient) -> None:
    receiver = Receiver().install(hook_client)
    created = create(hook_client)
    hook_client.post(f"/api/v1/webhooks/{created['id']}/test")
    with pytest.raises(AssertionError):
        verify(receiver.requests[0], "whsec_" + "0" * 64)


def test_each_endpoint_has_its_own_secret_and_renewing_replaces_it(hook_client: TestClient) -> None:
    receiver = Receiver().install(hook_client)
    first = create(hook_client, "https://127.0.0.1/one")
    second = create(hook_client, "https://127.0.0.1/two")
    assert first["signing_secret"] != second["signing_secret"]
    renewed = hook_client.post(f"/api/v1/webhooks/{first['id']}/rotate").json()
    assert renewed["signing_secret"] not in (first["signing_secret"], second["signing_secret"])
    hook_client.post(f"/api/v1/webhooks/{first['id']}/test")
    verify(receiver.requests[-1], renewed["signing_secret"])  # the new secret works
    with pytest.raises(AssertionError):
        verify(receiver.requests[-1], first["signing_secret"])  # the old one no longer does


def test_the_secret_does_not_change_between_restarts_with_the_same_key() -> None:
    from app.core.config import Settings
    from app.repositories.webhooks import Endpoint
    from app.services.webhooks import WebhookService

    def service(key: str) -> WebhookService:
        return WebhookService(None, Settings(webhook_signing_key=key))  # type: ignore[arg-type]

    endpoint = Endpoint("abc", "org", HOOK, 1, True)
    assert service(KEY).secret_for(endpoint) == service(KEY).secret_for(endpoint)
    assert service(KEY).secret_for(endpoint) != service("j" * 40).secret_for(endpoint)


# --- delivery --------------------------------------------------------------------------------------------


def test_a_server_error_is_tried_twice_and_recorded(hook_client: TestClient) -> None:
    receiver = Receiver(503, 503).install(hook_client)
    created = create(hook_client)
    result = hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result["ok"] is False and "503" in result["status"]
    assert len(receiver.requests) == 2
    item = hook_client.get("/api/v1/webhooks").json()["items"][0]
    assert item["consecutive_failures"] == 1 and "503" in item["last_status"]


def test_a_temporary_failure_that_then_succeeds_counts_as_delivered(hook_client: TestClient) -> None:
    receiver = Receiver(502, 200).install(hook_client)
    created = create(hook_client)
    assert hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()["ok"] is True
    assert len(receiver.requests) == 2


def test_a_client_error_is_not_retried_and_redirects_are_not_followed(hook_client: TestClient) -> None:
    receiver = Receiver(404).install(hook_client)
    created = create(hook_client)
    assert hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()["ok"] is False
    assert len(receiver.requests) == 1
    receiver = Receiver(302).install(hook_client)
    result = hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert "302" in result["status"] and "not followed" in result["status"]
    assert len(receiver.requests) == 1


def test_a_connection_failure_is_reported_plainly(hook_client: TestClient) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    created = create(hook_client)
    state = hook_client.app.state.s  # type: ignore[attr-defined]
    state.webhooks.transport = httpx.MockTransport(refuse)
    state.webhooks.retry_delay = 0
    result = hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result == {"ok": False, "status": "Failed: could not connect."}


def test_an_endpoint_that_keeps_failing_is_switched_off_until_a_person_turns_it_on(
    hook_client: TestClient,
) -> None:
    Receiver(500).install(hook_client)
    created = create(hook_client)
    state = hook_client.app.state.s  # type: ignore[attr-defined]
    for _ in range(AUTO_DISABLE_AFTER):
        state.webhook_repo.record_attempt(created["id"], False, "Failed (HTTP 500).")
    item = hook_client.get("/api/v1/webhooks").json()["items"][0]
    assert item["enabled"] is False and item["consecutive_failures"] == AUTO_DISABLE_AFTER
    back = hook_client.put(f"/api/v1/webhooks/{created['id']}", json={"enabled": True}).json()
    assert back["enabled"] is True and back["consecutive_failures"] == 0


def test_the_address_is_checked_again_at_delivery_time(hook_client: TestClient) -> None:
    receiver = Receiver().install(hook_client)
    created = create(hook_client)
    state = hook_client.app.state.s  # type: ignore[attr-defined]
    state.settings.allow_private_targets = False  # the name now "points" at an internal address
    result = hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result["ok"] is False and result["status"].startswith("Blocked")
    assert receiver.requests == []


def test_test_messages_are_rate_limited(hook_client: TestClient) -> None:
    Receiver().install(hook_client)
    created = create(hook_client)
    codes = [hook_client.post(f"/api/v1/webhooks/{created['id']}/test").status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_deleting_removes_the_endpoint_and_is_audited(hook_client: TestClient) -> None:
    created = create(hook_client)
    assert hook_client.delete(f"/api/v1/webhooks/{created['id']}").status_code == 204
    assert hook_client.get("/api/v1/webhooks").json()["items"] == []
    assert hook_client.delete(f"/api/v1/webhooks/{created['id']}").status_code == 404
    events = [e["event_type"] for e in hook_client.get("/api/v1/audit-events").json()["items"]]
    assert "webhook.created" in events and "webhook.deleted" in events


# --- the alert -------------------------------------------------------------------------------------------


def test_a_worse_scan_sends_a_signed_alert_and_a_quiet_one_sends_nothing(
    hook_client: TestClient, mock_server: str, mailer: CapturingMailer
) -> None:
    receiver = Receiver().install(hook_client)
    secret = create(hook_client)["signing_secret"]
    tid = target_id_of(hook_client)
    body = {"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"}
    hook_client.put(f"/api/v1/schedules/{tid}", json=body).raise_for_status()
    run_cron(hook_client)
    assert receiver.requests == []  # the first scan of a site never alerts
    hook_client.put(
        f"/api/v1/schedules/{tid}", json={**body, "url": f"{mock_server}/plain"}
    ).raise_for_status()
    make_due(hook_client)
    run_cron(hook_client)
    assert len(receiver.requests) == 1
    payload = verify(receiver.requests[0], secret)
    assert payload["event"] == "scan.alert"
    assert payload["site"] == {"host": "127.0.0.1"}
    assert payload["new_findings"] and {"id", "severity", "title"} == set(payload["new_findings"][0])
    assert payload["scan"]["score"] is not None and "/#/findings?scan=" in payload["scan"]["url"]
    assert "SECRETVALUE123" not in json.dumps(payload)  # evidence is never sent
    make_due(hook_client)
    run_cron(hook_client)  # same result as last time
    assert len(receiver.requests) == 1


def test_switching_notifications_off_stops_webhooks_too(hook_client: TestClient, mock_server: str) -> None:
    receiver = Receiver().install(hook_client)
    create(hook_client)
    tid = target_id_of(hook_client)
    body = {"frequency": "daily", "notify": False, "url": f"{mock_server}/hardened"}
    hook_client.put(f"/api/v1/schedules/{tid}", json=body).raise_for_status()
    run_cron(hook_client)
    hook_client.put(
        f"/api/v1/schedules/{tid}", json={**body, "url": f"{mock_server}/plain"}
    ).raise_for_status()
    make_due(hook_client)
    run_cron(hook_client)
    assert receiver.requests == []


def test_a_disabled_endpoint_gets_no_alerts_and_a_broken_one_does_not_stop_the_run(
    hook_client: TestClient, mock_server: str
) -> None:
    receiver = Receiver(500).install(hook_client)
    off = create(hook_client, "https://127.0.0.1/off")
    create(hook_client, "https://127.0.0.1/broken")
    hook_client.put(f"/api/v1/webhooks/{off['id']}", json={"enabled": False}).raise_for_status()
    tid = target_id_of(hook_client)
    body = {"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"}
    hook_client.put(f"/api/v1/schedules/{tid}", json=body).raise_for_status()
    run_cron(hook_client)
    hook_client.put(
        f"/api/v1/schedules/{tid}", json={**body, "url": f"{mock_server}/plain"}
    ).raise_for_status()
    make_due(hook_client)
    summary = run_cron(hook_client)
    assert summary["scans_started"] == 1
    assert {r.url.path for r in receiver.requests} == {"/broken"}


def test_the_cron_endpoint_constant_is_unchanged() -> None:
    assert CRON == "/api/v1/internal/run-due"


# --- delivery history ------------------------------------------------------------------------------------


def test_every_delivery_is_listed_with_its_outcome_and_no_message_content(hook_client: TestClient) -> None:
    Receiver(500, 200).install(hook_client)
    created = create(hook_client)
    assert hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()["ok"] is True
    Receiver(404).install(hook_client)
    assert hook_client.post(f"/api/v1/webhooks/{created['id']}/test").json()["ok"] is False
    items = hook_client.get(f"/api/v1/webhooks/{created['id']}/deliveries").json()
    assert [(i["ok"], i["event"], i["attempts"]) for i in items] == [
        (False, "webhook.test", 1),
        (True, "webhook.test", 2),
    ]
    assert items[0]["status"].startswith("Failed (HTTP 404)")
    assert all(len(i["delivery_id"]) == 32 for i in items)
    text = hook_client.get(f"/api/v1/webhooks/{created['id']}/deliveries").text
    assert "abc123-secret-token" not in text and "whsec_" not in text and "127.0.0.1" not in text


def test_only_the_most_recent_deliveries_are_kept(hook_client: TestClient) -> None:
    from app.repositories.webhooks import KEEP_DELIVERIES

    Receiver().install(hook_client)
    created = create(hook_client)
    state = hook_client.app.state.s  # type: ignore[attr-defined]
    for n in range(KEEP_DELIVERIES + 5):
        state.webhook_repo.record_attempt(created["id"], True, f"Delivered #{n}", event="scan.alert")
    items = hook_client.get(f"/api/v1/webhooks/{created['id']}/deliveries").json()
    assert len(items) == KEEP_DELIVERIES
    assert items[0]["status"] == f"Delivered #{KEEP_DELIVERIES + 4}"
    assert hook_client.get("/api/v1/webhooks").json()["items"][0]["last_status"].startswith("Delivered #")


def test_deliveries_of_another_workspace_or_a_missing_address_are_not_found(
    hook_client: TestClient,
) -> None:
    Receiver().install(hook_client)
    created = create(hook_client)
    hook_client.post(f"/api/v1/webhooks/{created['id']}/test")
    with TestClient(hook_client.app) as bob:
        signup(bob, "bob@example.com", "Bob Org")
        assert bob.get(f"/api/v1/webhooks/{created['id']}/deliveries").status_code == 404
    assert hook_client.get("/api/v1/webhooks/" + "f" * 32 + "/deliveries").status_code == 404
    assert hook_client.get("/api/v1/webhooks/bad-id/deliveries").status_code == 404
    with TestClient(hook_client.app) as anonymous:
        assert anonymous.get(f"/api/v1/webhooks/{created['id']}/deliveries").status_code == 401


def test_the_history_is_removed_with_its_address(hook_client: TestClient) -> None:
    from sqlalchemy import func, select

    from app.models.webhook import WebhookDeliveryRow

    Receiver().install(hook_client)
    created = create(hook_client)
    hook_client.post(f"/api/v1/webhooks/{created['id']}/test")
    state = hook_client.app.state.s  # type: ignore[attr-defined]
    with state.webhook_repo._session() as session:
        assert session.scalar(select(func.count()).select_from(WebhookDeliveryRow)) == 1
    assert hook_client.delete(f"/api/v1/webhooks/{created['id']}").status_code == 204
    with state.webhook_repo._session() as session:
        assert session.scalar(select(func.count()).select_from(WebhookDeliveryRow)) == 0


# --- Slack ------------------------------------------------------------------------------------------------

# Made-up test values, assembled at run time so that no secret-shaped text is stored in the repository
# (GitHub push protection rightly treats a literal Slack webhook address as a secret).
_PATH = "/".join(("services", "T" + "0" * 8, "B" + "0" * 8, "x" * 24))
SLACK = f"https://hooks.slack.com/{_PATH}"


@pytest.fixture
def slack_client(hook_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """hooks.slack.com resolves to a public address here, so no real DNS lookup is needed."""
    import ipaddress

    async def resolve(host: str, port: int):  # type: ignore[no-untyped-def]
        return [ipaddress.ip_address("34.200.1.1")]

    monkeypatch.setattr("app.security.target.resolve_host", resolve)
    return hook_client


def test_a_slack_address_is_accepted_without_a_signing_secret_and_never_shown_in_full(
    slack_client: TestClient,
) -> None:
    response = slack_client.post("/api/v1/webhooks", json={"url": SLACK, "kind": "slack"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "slack" and body["signing_secret"] is None
    assert body["address"] == "https://hooks.slack.com/…"
    listing = slack_client.get("/api/v1/webhooks").text
    assert "x" * 24 not in listing and "T" + "0" * 8 not in listing


@pytest.mark.parametrize(
    "url",
    [
        f"https://evil.example.com/{_PATH}",
        f"https://hooks.slack.com.evil.example.com/{_PATH}",
        f"https://hooks.slack.com@evil.example.com/{_PATH}",
        f"http://hooks.slack.com/{_PATH}",
        f"https://hooks.slack.com/other/{_PATH.split('/', 1)[1]}",
        f"https://hooks.slack.com/{_PATH}/extra",
        f"https://hooks.slack.com:8443/{_PATH}",
        f"https://hooks.slack.com/{_PATH}?x=http://169.254.169.254",
        "https://127.0.0.1/hook",
    ],
)
def test_a_slack_address_must_be_exactly_a_slack_incoming_webhook(slack_client: TestClient, url: str) -> None:
    response = slack_client.post("/api/v1/webhooks", json={"url": url, "kind": "slack"})
    assert response.status_code == 400, response.text
    assert slack_client.get("/api/v1/webhooks").json()["items"] == []


def test_a_slack_message_is_plain_text_and_carries_no_signature(slack_client: TestClient) -> None:
    receiver = Receiver().install(slack_client)
    created = slack_client.post("/api/v1/webhooks", json={"url": SLACK, "kind": "slack"}).json()
    result = slack_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result["ok"] is True, result
    sent = receiver.requests[0]
    body = json.loads(sent.content)
    assert list(body) == ["text"] and "test message" in body["text"].lower()
    assert "x-securescope-signature" not in sent.headers
    assert sent.url.host == "34.200.1.1" and sent.headers["host"] == "hooks.slack.com"
    history = slack_client.get(f"/api/v1/webhooks/{created['id']}/deliveries").json()
    assert history[0]["ok"] is True


def test_a_slack_alert_lists_the_facts_escapes_markup_and_leaves_out_evidence() -> None:
    from app.services.webhooks import slack_text

    text = slack_text(
        "scan.alert",
        {
            "site": {"host": "a<b>&.example"},
            "scan": {
                "id": "x",
                "score": 72,
                "grade": "C",
                "url": "https://getsecurescope.com/#/findings?scan=x",
            },
            "reasons": ["1 new finding since the previous scan."],
            "new_findings": [{"id": "SS-1", "severity": "high", "title": "Bad <b>header</b> & more"}],
        },
    )
    assert "a&lt;b&gt;&amp;.example" in text and "Bad &lt;b&gt;header&lt;/b&gt; &amp; more" in text
    assert "<b>" not in text
    assert "Score 72 (grade C)" in text and "|Open the scan in SecureScope>" in text
    assert "evidence" not in text.lower()


def test_a_slack_address_has_no_secret_to_renew(slack_client: TestClient) -> None:
    Receiver().install(slack_client)
    created = slack_client.post("/api/v1/webhooks", json={"url": SLACK, "kind": "slack"}).json()
    assert slack_client.post(f"/api/v1/webhooks/{created['id']}/rotate").status_code == 400


def test_the_address_is_checked_again_before_every_slack_delivery(
    slack_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ipaddress

    receiver = Receiver().install(slack_client)
    created = slack_client.post("/api/v1/webhooks", json={"url": SLACK, "kind": "slack"}).json()

    async def internal(host: str, port: int):  # type: ignore[no-untyped-def]
        return [ipaddress.ip_address("10.0.0.5")]

    monkeypatch.setattr("app.security.target.resolve_host", internal)
    slack_client.app.state.s.settings.allow_private_targets = False  # type: ignore[attr-defined]
    result = slack_client.post(f"/api/v1/webhooks/{created['id']}/test").json()
    assert result["ok"] is False and result["status"].startswith("Blocked")
    assert receiver.requests == []
