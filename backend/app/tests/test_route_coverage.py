"""Every route that takes an identifier must be in the cross-customer attack list, or be listed here with a reason.

A new endpoint such as /things/{id} fails this test until someone decides how Bob is kept out of Alice's thing.
"""

from __future__ import annotations

import re
from typing import Any

from app.main import create_app
from app.tests.test_cross_customer import API, attacks

# Routes that take an id but are not ownership-checked by a signed-in member, with the reason.
PUBLIC_OR_OWN_SCOPE = {
    # Bearer secrets or public names: possession of the unguessable value is the credential, and the
    # answer for a wrong one is the same as for a missing one (test_agency, test_integrations).
    "GET /shared/{}/report.pdf",
    "GET /badges/{}",
    "GET /shared/{}",
    # Provider names, not records (test_oauth).
    "GET /auth/oauth/{}/start",
    "GET /auth/oauth/{}/callback",
    # A CI token only reaches scans of its own workspace (test_cross_customer, test_integrations).
    "GET /ci/scans/{}",
    # App Scanning: every query takes the workspace id and answers 404 for another one (test_appscan_routes).
    "POST /app/projects/{}/archive",
    "GET /app/scans/{}",
}


def _normalise(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_every_route_with_an_id_is_attacked_by_the_cross_customer_test_or_explained(
    make_settings: Any,
) -> None:
    app = create_app(make_settings())
    declared = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith(API) or "{" not in path:
            continue
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                declared.add((method.upper(), _normalise(path[len(API) :])))
    assert len(declared) > 20, "the route list could not be read, so nothing would be checked"

    ids = {
        "target": "ZTARGETZ",
        "scan": "ZSCANZ",
        "hook": "ZHOOKZ",
        "fingerprint": "ZFINGERZ",
        "org": "ZORGZ",
        "client": "ZCLIENTZ",
        "share": "ZSHAREZ",
        "invitation": "ZINVITEZ",
        "owner": "ZOWNERZ",
        "session": "ZSESSIONZ",
    }
    world = {**ids, "token": {"id": "ZTOKENZ"}}
    placeholders = [*ids.values(), "ZTOKENZ"]
    attacked = set()
    for method, path, _ in attacks(world):
        path = path.split("?")[0]
        for value in placeholders:
            path = path.replace(value, "{}")
        attacked.add((method, path))
    explained = {tuple(item.split(" ", 1)) for item in PUBLIC_OR_OWN_SCOPE}
    explained_norm = {(m, _normalise(p)) for m, p in explained}
    missing = sorted(d for d in declared if d not in attacked and d not in explained_norm)
    assert missing == [], f"routes with an id and no cross-customer attack or reason: {missing}"
