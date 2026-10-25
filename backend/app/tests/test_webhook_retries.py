"""An alert that could not be delivered is tried again later, safely and a limited number of times."""

# ruff: noqa: F811
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models.webhook import WebhookRetryRow
from app.repositories.webhooks import RETRY_DELAYS, RETRY_MAX_PENDING
from app.tests.test_schedules import make_due, run_cron, target_id_of
from app.tests.test_webhooks import Receiver, create, hook_client, verify  # noqa: F401


class Flaky(Receiver):
    """Answers with whatever `status` is set to right now."""

    def __init__(self, status: int = 503) -> None:
        super().__init__()
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status)


def state_of(client: TestClient) -> Any:
    return client.app.state.s  # type: ignore[attr-defined]


def retries(client: TestClient) -> list[Any]:
    with state_of(client).webhook_repo._session() as session:
        return list(session.scalars(select(WebhookRetryRow).order_by(WebhookRetryRow.created_at)))


def make_retry_due(client: TestClient, minutes_ago: int = 1) -> None:
    with state_of(client).webhook_repo._session.begin() as session:
        session.execute(
            update(WebhookRetryRow).values(next_attempt_at=datetime.now(UTC) - timedelta(minutes=minutes_ago))
        )


def trigger_alert(client: TestClient, mock_server: str) -> None:
    """A first scan, then a worse one: the second sends an alert."""
    tid = target_id_of(client)
    body = {"frequency": "daily", "notify": True, "url": f"{mock_server}/hardened"}
    client.put(f"/api/v1/schedules/{tid}", json=body).raise_for_status()
    run_cron(client)
    client.put(f"/api/v1/schedules/{tid}", json={**body, "url": f"{mock_server}/plain"}).raise_for_status()
    make_due(client)
    run_cron(client)


def install(client: TestClient, receiver: Flaky) -> Flaky:
    receiver.install(client)
    return receiver


def listed(client: TestClient, webhook_id: str) -> list[dict[str, Any]]:
    return client.get(f"/api/v1/webhooks/{webhook_id}/deliveries").json()  # type: ignore[no-any-return]


def test_a_failed_alert_is_queued_and_not_marked_delivered(hook_client: TestClient, mock_server: str) -> None:
    receiver = install(hook_client, Flaky(503))
    hook = create(hook_client)
    trigger_alert(hook_client, mock_server)
    assert len(receiver.requests) == 2  # the two immediate attempts
    queued = retries(hook_client)
    assert len(queued) == 1 and queued[0].retries == 0
    assert queued[0].next_attempt_at.replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(minutes=4)
    first = listed(hook_client, hook["id"])[0]
    assert first["ok"] is False and "Will try again" in first["status"]


def test_a_stored_alert_holds_only_what_the_signed_message_holds(
    hook_client: TestClient, mock_server: str
) -> None:
    install(hook_client, Flaky(503))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    payload = json.loads(retries(hook_client)[0].payload)
    assert set(payload) == {"site", "scan", "reasons", "new_findings"}
    assert "SECRETVALUE123" not in json.dumps(payload)
    assert "whsec_" not in json.dumps(payload)


def test_nothing_is_sent_before_the_retry_is_due(hook_client: TestClient, mock_server: str) -> None:
    receiver = install(hook_client, Flaky(503))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    sent = len(receiver.requests)
    run_cron(hook_client)
    assert len(receiver.requests) == sent and len(retries(hook_client)) == 1


def test_a_due_retry_is_delivered_once_with_the_same_delivery_id(
    hook_client: TestClient, mock_server: str
) -> None:
    receiver = install(hook_client, Flaky(503))
    hook = create(hook_client)
    trigger_alert(hook_client, mock_server)
    first_id = verify(receiver.requests[0], hook["signing_secret"])["delivery_id"]
    receiver.status = 200
    make_retry_due(hook_client)
    run_cron(hook_client)
    assert retries(hook_client) == []
    last = receiver.requests[-1]
    body = verify(last, hook["signing_secret"])  # signed again, with a fresh timestamp
    assert body["event"] == "scan.alert" and body["delivery_id"] == first_id
    assert last.headers["x-securescope-delivery"] == first_id
    newest = listed(hook_client, hook["id"])[0]
    assert newest["ok"] is True and newest["status"].startswith("Retry 1: Delivered")
    sent = len(receiver.requests)
    make_retry_due(hook_client)
    run_cron(hook_client)
    assert len(receiver.requests) == sent  # nothing left to send


def test_it_gives_up_after_the_last_retry(hook_client: TestClient, mock_server: str) -> None:
    receiver = install(hook_client, Flaky(503))
    hook = create(hook_client)
    trigger_alert(hook_client, mock_server)
    after_first = len(receiver.requests)
    for number in range(1, len(RETRY_DELAYS) + 1):
        assert len(retries(hook_client)) == 1
        make_retry_due(hook_client)
        run_cron(hook_client)
        assert len(receiver.requests) == after_first + number  # one request per retry
    assert retries(hook_client) == []
    assert "Giving up" in listed(hook_client, hook["id"])[0]["status"]


def test_a_permanent_error_is_not_queued(hook_client: TestClient, mock_server: str) -> None:
    install(hook_client, Flaky(404))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    assert retries(hook_client) == []


def test_test_messages_are_never_queued(hook_client: TestClient) -> None:
    install(hook_client, Flaky(503))
    hook = create(hook_client)
    assert hook_client.post(f"/api/v1/webhooks/{hook['id']}/test").json()["ok"] is False
    assert retries(hook_client) == []


def test_retries_of_a_switched_off_endpoint_are_dropped_unsent(
    hook_client: TestClient, mock_server: str
) -> None:
    receiver = install(hook_client, Flaky(503))
    hook = create(hook_client)
    trigger_alert(hook_client, mock_server)
    hook_client.put(f"/api/v1/webhooks/{hook['id']}", json={"enabled": False}).raise_for_status()
    sent = len(receiver.requests)
    make_retry_due(hook_client)
    run_cron(hook_client)
    assert retries(hook_client) == [] and len(receiver.requests) == sent


def test_a_day_old_alert_is_removed_without_being_sent(hook_client: TestClient, mock_server: str) -> None:
    receiver = install(hook_client, Flaky(503))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    sent = len(receiver.requests)
    with state_of(hook_client).webhook_repo._session.begin() as session:
        session.execute(
            update(WebhookRetryRow).values(
                created_at=datetime.now(UTC) - timedelta(hours=25),
                next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
    run_cron(hook_client)
    assert retries(hook_client) == [] and len(receiver.requests) == sent


def test_two_overlapping_runs_cannot_both_take_a_retry(hook_client: TestClient, mock_server: str) -> None:
    install(hook_client, Flaky(503))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    make_retry_due(hook_client)
    repo = state_of(hook_client).webhook_repo
    assert len(repo.claim_due_retries(datetime.now(UTC), 10)) == 1
    assert repo.claim_due_retries(datetime.now(UTC), 10) == []


def test_one_endpoint_cannot_queue_more_than_the_limit(hook_client: TestClient) -> None:
    hook = create(hook_client)
    repo = state_of(hook_client).webhook_repo
    results = [
        repo.enqueue_retry(hook["id"], f"d{i}", "scan.alert", "{}") for i in range(RETRY_MAX_PENDING + 3)
    ]
    assert results.count(True) == RETRY_MAX_PENDING and results[-1] is False


@pytest.mark.parametrize("code", [429, 500, 502])
def test_these_failures_are_worth_trying_again(hook_client: TestClient, mock_server: str, code: int) -> None:
    install(hook_client, Flaky(code))
    create(hook_client)
    trigger_alert(hook_client, mock_server)
    assert len(retries(hook_client)) == 1


def test_a_retry_that_meets_a_permanent_error_stops(hook_client: TestClient, mock_server: str) -> None:
    receiver = install(hook_client, Flaky(503))
    hook = create(hook_client)
    trigger_alert(hook_client, mock_server)
    receiver.status = 404  # the receiver has since removed the address
    make_retry_due(hook_client)
    run_cron(hook_client)
    assert retries(hook_client) == []
    assert "Giving up" in listed(hook_client, hook["id"])[0]["status"]
