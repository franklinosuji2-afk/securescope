"""After an account is deleted, no table keeps a row that points at the person or at a workspace that went with them.

The sweep reads the schema, so a table added later is checked without anyone remembering to add it here. It also
looks for the person's email, workspace name and webhook address as text in every column of every table.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, func, select

from app.billing.lifecycle import SubscriptionState
from app.database.base import Base
from app.main import create_app
from app.tests.conftest import PASSWORD, signup, trust_host
from app.tests.test_client_accounts import confirm_email
from app.tests.test_finding_lifecycle import API, member_client
from app.tests.test_tenancy import finished_scan, org_of

EMAIL = "sweep-alice@example.com"
ORG_NAME = "Sweep Alice Workspace"
HOOK_SECRET = "sweep-secret-path-4821"


def references(table: Table, target: str) -> list[str]:
    return [c.name for c in table.columns if any(fk.column.table.name == target for fk in c.foreign_keys)]


def sweep(client: TestClient, user_id: str | None, org_id: str | None) -> list[str]:
    """Rows that still point at the removed person or workspace, as 'table.column: n'."""
    state = client.app.state.s  # type: ignore[attr-defined]
    found = []
    with state.engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for target, value in (("users", user_id), ("organizations", org_id)):
                if value is None:
                    continue
                for column in references(table, target):
                    n = conn.execute(
                        select(func.count()).select_from(table).where(table.c[column] == value)
                    ).scalar()
                    if n:
                        found.append(f"{table.name}.{column}: {n}")
    return found


def text_left(client: TestClient, needles: tuple[str, ...]) -> list[str]:
    state = client.app.state.s  # type: ignore[attr-defined]
    hits = []
    with state.engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not str(column.type).upper().startswith(("VARCHAR", "TEXT", "STRING")):
                    continue
                for needle in needles:
                    n = conn.execute(
                        select(func.count()).select_from(table).where(column.like(f"%{needle}%"))
                    ).scalar()
                    if n:
                        hits.append(f"{table.name}.{column.name} contains {needle[:12]}: {n}")
    return hits


@pytest.fixture
def app_client(make_settings, mailer, mock_server):  # type: ignore[no-untyped-def]
    settings = make_settings(
        require_verified_email=True,
        allow_private_targets=True,
        request_timeout_seconds=1.0,
        webhook_signing_key="k" * 40,
        cron_secret="c" * 40,
    )
    with TestClient(create_app(settings, mailer)) as client:
        yield client


def populate(client: TestClient, mock_server: str) -> dict[str, str]:
    """Everything a customer can create, once."""
    org = org_of(client)
    tid = trust_host(client, "127.0.0.1", org)
    scan = finished_scan(client, mock_server)
    assert (
        client.put(
            f"{API}/schedules/{tid}", json={"frequency": "daily", "url": f"{mock_server}/plain"}
        ).status_code
        == 200
    )
    hook = client.post(f"{API}/webhooks", json={"url": f"https://127.0.0.1/{HOOK_SECRET}"})
    assert hook.status_code == 201, hook.text
    client.post(f"{API}/webhooks/{hook.json()['id']}/test")  # leaves a delivery record
    assert client.post(f"{API}/api-tokens", json={"name": "ci"}).status_code == 201
    assert client.put(f"{API}/badges/{tid}", json={"enabled": True, "renew": False}).status_code == 200
    assert (
        client.post(
            f"{API}/agency/clients", json={"name": "Sweep client", "contact_email": "c@x.example"}
        ).status_code
        == 201
    )
    assert client.post(f"{API}/agency/scans/{scan}/shares", json={"days": 7}).status_code == 201
    assert client.put(f"{API}/feedback", json={"rating": 4, "message": "sweep feedback"}).status_code in (
        200,
        201,
    )
    state = client.app.state.s  # type: ignore[attr-defined]
    state.billing.save_subscription(
        org,
        "sub_sweep",
        SubscriptionState(
            provider="test",
            plan_id="professional",
            status="active",
            current_period_end=None,
            cancel_at_period_end=False,
            pending_plan_id=None,
        ),
    )
    state.billing.record_event("test", "evt_sweep", "subscription.created", org)
    return {"org": org, "scan": scan}


def test_a_deleted_account_leaves_no_row_and_no_text_behind(
    app_client: TestClient, mailer: Any, mock_server: str
) -> None:
    with TestClient(app_client.app) as alice:
        signup(alice, EMAIL, ORG_NAME)
        confirm_email(alice, mailer, EMAIL)
        world = populate(alice, mock_server)
        user_id = alice.get(f"{API}/auth/me").json()["id"]
        # A bystander who must be untouched.
        with TestClient(app_client.app) as bob:
            signup(bob, "sweep-bob@example.com", "Bob Workspace")
            confirm_email(bob, mailer, "sweep-bob@example.com")
            bob_org = org_of(bob)
            # The sweep is not blind: before deleting, it finds plenty.
            assert len(sweep(app_client, user_id, world["org"])) >= 12
            assert len(text_left(app_client, (EMAIL, ORG_NAME, HOOK_SECRET))) >= 3
            gone = alice.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
            assert gone.status_code == 204, gone.text
            assert sweep(app_client, user_id, world["org"]) == []
            assert (
                text_left(app_client, (EMAIL, ORG_NAME, HOOK_SECRET, "sweep feedback", "Sweep client")) == []
            )
            assert org_of(bob) == bob_org  # Bob is still there


def test_a_member_who_leaves_a_shared_workspace_leaves_nothing_pointing_at_them(
    app_client: TestClient, mailer: Any, mock_server: str
) -> None:
    with TestClient(app_client.app) as alice:
        signup(alice, EMAIL, ORG_NAME)
        confirm_email(alice, mailer, EMAIL)
        world = populate(alice, mock_server)
        mate = member_client(alice, world["org"], "sweep-mate@example.com", "ADMIN")
        mate_id = mate.get(f"{API}/auth/me").json()["id"]
        mate.post(f"{API}/api-tokens", json={"name": "mate ci"}, headers={"X-Organization-Id": world["org"]})
        mate.post(
            f"{API}/agency/clients", json={"name": "Mate client"}, headers={"X-Organization-Id": world["org"]}
        )
        mate.put(f"{API}/feedback", json={"rating": 5, "message": "mate feedback"})
        gone = mate.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
        assert gone.status_code == 204, gone.text
        assert sweep(app_client, mate_id, None) == []
        assert text_left(app_client, ("sweep-mate@example.com", "mate feedback")) == []
        # The workspace and Alice's things are intact.
        assert alice.get(f"{API}/scans/{world['scan']}").status_code == 200
        assert len(alice.get(f"{API}/webhooks").json()["items"]) == 1


def test_every_reference_to_a_person_or_workspace_is_deleted_or_cleared_by_the_database() -> None:
    """If the application code misses a table, the database still removes or detaches the row."""
    weak = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name in ("users", "organizations") and (fk.ondelete or "").upper() not in (
                    "CASCADE",
                    "SET NULL",
                ):
                    weak.append(f"{table.name}.{column.name} -> {fk.column.table.name} ({fk.ondelete})")
    assert weak == []
