"""docs/API.md must describe every route the API really has, so the documentation cannot silently fall behind."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

DOCS = Path(__file__).resolve().parents[3] / "docs"


def _normal(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.split("?")[0])


def test_every_route_is_described_in_the_api_docs(make_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(make_settings())
    with TestClient(app):
        routes = {_normal(p.removeprefix("/api/v1")) for p in app.openapi()["paths"]}
    text = "\n".join((DOCS / name).read_text() for name in ("API.md", "INTEGRATIONS.md"))
    documented = {_normal(m) for m in re.findall(r"`(/[A-Za-z0-9/_{}.\-]*(?:\?[^`]*)?)`", text)}
    # The public badge image is documented as /badges/{token}.svg.
    documented |= {d.replace("{}.svg", "{}") for d in documented}
    missing = sorted(r for r in routes if r not in documented)
    assert not missing, f"routes missing from docs/API.md: {missing}"
