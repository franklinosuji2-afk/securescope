"""Deleting an account must leave no personal data behind in the newer tables either (schedules, API tokens,
webhook addresses, badges, clients, plan records), and must keep a shared workspace's own things."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models.agency import ClientRow
from app.models.billing import OrganizationPlanRow
from app.models.integration import ApiTokenRow, SiteBadgeRow
from app.models.schedule import ScanScheduleRow
from app.models.target import TargetRow
from app.models.webhook import WebhookEndpointRow
from app.tests.conftest import PASSWORD, CapturingMailer, signup, trust_host
from app.tests.test_client_accounts import confirm_email
from app.tests.test_finding_lifecycle import API, member_client

TABLES: tuple[Any, ...] = (
    ScanScheduleRow,
    ApiTokenRow,
    SiteBadgeRow,
    WebhookEndpointRow,
    ClientRow,
    OrganizationPlanRow,
    TargetRow,
)


@pytest.fixture
def app_client(make_settings, mailer) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    settings = make_settings(require_verified_email=True, allow_private_targets=True)
    with TestClient(create_app(settings, mailer)) as client:
        yield client


def counts(client: TestClient) -> dict[str, int]:
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session() as session:
        return {m.__tablename__: session.scalar(select(func.count()).select_from(m)) or 0 for m in TABLES}


def fill_workspace(client: TestClient, host: str, created_by: str | None) -> str:
    """Adds one row to every newer table for the workspace of `client`."""
    org: str = client.get(f"{API}/auth/me").json()["organizations"][0]["id"]
    target_id = trust_host(client, host, org)
    now = datetime.now(UTC)
    state = client.app.state.s  # type: ignore[attr-defined]
    with state.report_service.reports._session.begin() as session:
        session.add(
            ScanScheduleRow(
                id=f"sch{host[:20]}".ljust(32, "0"),
                organization_id=org,
                target_id=target_id,
                url=f"https://{host}/",
                frequency="daily",
                notify=True,
                next_run_at=now,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ApiTokenRow(
                id=f"tok{host[:20]}".ljust(32, "0"),
                organization_id=org,
                created_by=created_by,
                name="ci",
                token_hash=f"{host:0<64}"[:64],
                prefix="ssk_abc",
                created_at=now,
            )
        )
        session.add(
            SiteBadgeRow(
                id=f"bad{host[:20]}".ljust(32, "0"),
                organization_id=org,
                target_id=target_id,
                token=f"badge-{host}",
                created_at=now,
            )
        )
        session.add(
            WebhookEndpointRow(
                id=f"web{host[:20]}".ljust(32, "0"),
                organization_id=org,
                url="https://hooks.example.org/secret-path",
                created_by=created_by,
                created_at=now,
            )
        )
        session.add(
            ClientRow(
                id=f"cli{host[:20]}".ljust(32, "0"),
                organization_id=org,
                name=f"Client {host}",
                contact_email="client@example.org",
                created_at=now,
                updated_at=now,
            )
        )
    return org


def user_id(client: TestClient) -> str:
    user: dict[str, Any] = client.get(f"{API}/auth/me").json()
    return str(user["id"])


def test_deleting_an_account_also_removes_schedules_tokens_webhooks_badges_and_clients(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    with TestClient(app_client.app) as alice:
        signup(alice, "alice@example.com", "alice workspace")
        confirm_email(alice, mailer, "alice@example.com")
        fill_workspace(alice, "alice-site.example", user_id(alice))
        with TestClient(app_client.app) as bob:
            signup(bob, "bob@example.com", "bob workspace")
            confirm_email(bob, mailer, "bob@example.com")
            fill_workspace(bob, "bob-site.example", user_id(bob))
            assert all(n == 2 for n in counts(alice).values() if n)
            gone = alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
            assert gone.status_code == 204
            left = counts(bob)
            # Only Bob's rows remain: one of each (the plan record is created on demand).
            assert left["scan_schedules"] == 1 and left["api_tokens"] == 1 and left["site_badges"] == 1
            assert left["webhook_endpoints"] == 1 and left["clients"] == 1 and left["targets"] == 1


def test_a_member_leaving_a_shared_workspace_takes_their_tokens_but_not_the_workspace_things(
    app_client: TestClient, mailer: CapturingMailer
) -> None:
    with TestClient(app_client.app) as alice:
        signup(alice, "alice@example.com", "alice workspace")
        confirm_email(alice, mailer, "alice@example.com")
        org = fill_workspace(alice, "shared-site.example", user_id(alice))
        mate = member_client(alice, org, "mate@example.com", "ADMIN")
        state = alice.app.state.s  # type: ignore[attr-defined]
        now = datetime.now(UTC)
        with state.report_service.reports._session.begin() as session:
            session.add(
                ApiTokenRow(
                    id="matetoken".ljust(32, "0"),
                    organization_id=org,
                    created_by=user_id(mate),
                    name="mate ci",
                    token_hash="m" * 64,
                    prefix="ssk_mate",
                    created_at=now,
                )
            )
        before = counts(alice)
        assert before["api_tokens"] == 2
        assert (
            mate.request(
                "DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"}
            ).status_code
            == 204
        )
        after = counts(alice)
        assert after["api_tokens"] == 1  # the leaver's token is gone; Alice's still works
        for table in ("scan_schedules", "site_badges", "webhook_endpoints", "clients", "targets"):
            assert after[table] == before[table]
