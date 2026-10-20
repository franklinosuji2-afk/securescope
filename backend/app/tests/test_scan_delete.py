"""Deleting finished scans."""

from __future__ import annotations

from app.tests.test_db_and_reports import make_org, make_repo
from app.tests.test_overview import complete


def test_a_finished_scan_can_be_deleted_with_its_findings(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    done = complete(repo, org, user, 90, [])
    assert repo.delete_scan(done, org) is True
    assert repo.get_scan(done, org) is None
    assert repo.delete_scan(done, org) is False


def test_other_organizations_and_active_scans_cannot_be_deleted(db_url: str) -> None:
    repo, (org, user) = make_repo(db_url), make_org(db_url)
    other_org, _ = make_org(db_url, "other@example.com")
    done = complete(repo, org, user, 90, [])
    assert repo.delete_scan(done, other_org) is False
    assert repo.get_scan(done, org) is not None
    active = repo.create_scan(org, user, "https://a.example/", "a.example")
    assert repo.delete_scan(active, org) is False
    assert repo.get_scan(active, org) is not None
