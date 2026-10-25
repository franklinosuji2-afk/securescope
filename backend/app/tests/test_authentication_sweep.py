"""Every route that is not deliberately public refuses a visitor with no credentials.

The list of public routes is written out here on purpose: a new route is private until someone adds it to this list.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app

# Public on purpose, with the reason. Everything else must answer 401 (or 403/404 for secret-gated routes).
PUBLIC = {
    ("GET", "/api/v1/health"): "liveness probe",
    ("GET", "/api/v1/ready"): "readiness probe",
    ("GET", "/api/v1/auth/providers"): "which sign-in buttons to show",
    ("GET", "/api/v1/badges/{filename}"): "public score badge, secret address",
    ("GET", "/api/v1/shared/{token}"): "shared report, secret link",
    ("GET", "/api/v1/shared/{token}/report.pdf"): "shared report, secret link",
    ("GET", "/api/v1/auth/oauth/{provider}/start"): "sign in with a provider",
    ("GET", "/api/v1/auth/oauth/{provider}/callback"): "sign in with a provider",
    ("GET", "/api/v1/invitations/preview"): "invitation link, secret token",
    ("POST", "/api/v1/analytics/collect"): "cookieless visit counter",
    ("POST", "/api/v1/auth/forgot-password"): "sign-in flow",
    ("POST", "/api/v1/auth/login"): "sign-in flow",
    ("POST", "/api/v1/auth/register"): "sign-in flow",
    ("POST", "/api/v1/auth/reset-password"): "sign-in flow",
    ("POST", "/api/v1/auth/verify-email"): "sign-in flow",
}


def test_every_route_refuses_a_visitor_unless_it_is_public_on_purpose(
    make_settings: Any, mailer: Any
) -> None:
    with TestClient(create_app(make_settings(), mailer)) as client:
        answers = []
        for path, operations in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
            for method in operations:
                if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                url = re.sub(r"\{[^}]+\}", "0" * 32, path)
                body: dict[str, Any] | None = {} if method.upper() in ("POST", "PUT", "PATCH") else None
                response = client.request(method.upper(), url, json=body)
                answers.append((response.status_code, method.upper(), path))
        assert len(answers) > 60
        assert [a for a in answers if a[0] >= 500] == []
        open_routes = {(m, p) for status, m, p in answers if status != 401}
        assert open_routes == set(PUBLIC), sorted(open_routes ^ set(PUBLIC))
