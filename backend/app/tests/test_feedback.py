"""Private feedback: one entry per person, editable and withdrawable, never public, never required."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tests.conftest import PASSWORD, signup

API = "/api/v1"
ADMIN = "boss@example.com"


@pytest.fixture
def app(make_settings, mailer):  # type: ignore[no-untyped-def]
    return create_app(make_settings(admin_email=ADMIN), mailer)


def admin_client(app, mailer) -> TestClient:  # type: ignore[no-untyped-def]
    admin = TestClient(app)
    admin.__enter__()
    signup(admin, ADMIN, "Boss Org")
    token = next(body for to, _s, body in mailer.sent if to == ADMIN).rsplit("token=", 1)[1].strip()
    assert admin.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    return admin


def test_nothing_is_invented(app, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app):
        admin = admin_client(app, mailer)
        summary = admin.get(f"{API}/feedback/summary").json()
        assert summary == {
            "count": 0,
            "average": None,
            "by_rating": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            "latest": [],
        }
        assert admin.get(f"{API}/feedback").json() is None


def test_valid_submission_edit_and_withdraw(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        first = alice.put(
            f"{API}/feedback", json={"rating": 4, "category": "reports", "message": "  Clear reports.  "}
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert (body["rating"], body["category"], body["message"]) == (4, "reports", "Clear reports.")
        assert alice.get(f"{API}/feedback").json()["rating"] == 4

        # A second submission replaces the first; it never creates a second entry.
        second = alice.put(f"{API}/feedback", json={"rating": 2})
        assert second.status_code == 200
        assert second.json()["created_at"] == body["created_at"]
        assert second.json()["rating"] == 2 and second.json()["message"] is None

        assert alice.delete(f"{API}/feedback").status_code == 204
        assert alice.get(f"{API}/feedback").json() is None
        assert alice.delete(f"{API}/feedback").status_code == 204  # withdrawing twice is harmless


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": 0},
        {"rating": 6},
        {"rating": -1},
        {"rating": 3.5},
        {"rating": "five"},
        {},
        {"rating": 3, "category": "not-a-category"},
        {"rating": 3, "message": "x" * 2001},
        {"rating": 3, "user_id": "someone-else"},
    ],
)
def test_invalid_submissions_are_rejected(app, payload) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        assert alice.put(f"{API}/feedback", json=payload).status_code == 422
        assert alice.get(f"{API}/feedback").json() is None


def test_text_is_stored_as_text_and_control_characters_are_dropped(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        sent = "<script>alert(1)</script>\x00 line one\nline two\x07"
        stored = alice.put(f"{API}/feedback", json={"rating": 5, "message": sent}).json()["message"]
        assert stored == "<script>alert(1)</script> line one\nline two"
        assert alice.put(f"{API}/feedback", json={"rating": 5, "message": "   "}).json()["message"] is None


def test_access_control(app, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as anonymous:
        for method, path in [("get", ""), ("put", ""), ("delete", ""), ("get", "/summary")]:
            kwargs = {"json": {"rating": 5}} if method == "put" else {}
            assert getattr(anonymous, method)(f"{API}/feedback{path}", **kwargs).status_code == 401
    with TestClient(app) as alice, TestClient(app) as bob:
        signup(alice, "alice@example.com", "Alice Org")
        signup(bob, "bob@example.com", "Bob Org")
        alice.put(f"{API}/feedback", json={"rating": 5, "message": "private note from alice"})
        # Bob sees nothing of Alice's and his own deletion does not touch hers.
        assert bob.get(f"{API}/feedback").json() is None
        assert bob.delete(f"{API}/feedback").status_code == 204
        assert alice.get(f"{API}/feedback").json()["message"] == "private note from alice"
        # An ordinary account cannot read the operator summary, and is not told it exists.
        assert bob.get(f"{API}/feedback/summary").status_code == 404
        assert alice.get(f"{API}/feedback/summary").status_code == 404


def test_operator_summary_has_no_names_or_emails(app, mailer) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as alice, TestClient(app) as bob:
        signup(alice, "alice@example.com", "Alice Org")
        signup(bob, "bob@example.com", "Bob Org")
        alice.put(f"{API}/feedback", json={"rating": 5, "category": "general", "message": "great"})
        bob.put(f"{API}/feedback", json={"rating": 3})
        admin = admin_client(app, mailer)
        summary = admin.get(f"{API}/feedback/summary").json()
        assert summary["count"] == 2
        assert summary["average"] == 4.0
        assert summary["by_rating"]["5"] == 1 and summary["by_rating"]["3"] == 1
        text = json.dumps(summary)
        for forbidden in ("alice", "bob", "example.com", "user_id", "Alice Org"):
            assert forbidden not in text


def test_feedback_is_never_required_and_leaves_with_the_account(app) -> None:  # type: ignore[no-untyped-def]
    with TestClient(app) as alice:
        signup(alice, "alice@example.com", "Alice Org")
        # No feedback was given, and deleting the account works regardless.
        assert alice.get(f"{API}/feedback").json() is None
    with TestClient(app) as carol:
        signup(carol, "carol@example.com", "Carol Org")
        carol.put(f"{API}/feedback", json={"rating": 1, "message": "gone with the account"})
        gone = carol.request("DELETE", f"{API}/account", json={"password": PASSWORD, "confirm": "DELETE"})
        assert gone.status_code == 204, gone.text
        state = carol.app.state.s  # type: ignore[attr-defined]
        assert state.feedback.summary().count == 0
