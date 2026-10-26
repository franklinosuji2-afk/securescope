"""Creates throwaway users for the load tests, each with a verified local target and one finished scan.

Run it once against the test database before `loadtest.py`, with `loadtest_mock.py` already running. It writes
the generated sign-in details to a file outside the repository. Local use only: it switches on the scanner's
test-only permission to reach 127.0.0.1, which the real service refuses.

    cd backend
    SECURESCOPE_DATABASE_URL=sqlite:////tmp/lt.db python -m app.database.migrate
    SECURESCOPE_DATABASE_URL=sqlite:////tmp/lt.db python ../scripts/loadtest_seed.py --users 20 --out /tmp/lt-users.json
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.main import create_app
from app.tests.conftest import CapturingMailer, trust_host
from fastapi.testclient import TestClient

MOCK = "http://127.0.0.1:8765/plain"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    database_url = os.environ.get("SECURESCOPE_DATABASE_URL", "")
    if not database_url:
        sys.exit("Set SECURESCOPE_DATABASE_URL to the test database.")
    if "neon" in database_url or "render" in database_url:
        sys.exit(
            "This looks like a hosted database. The load tests are for a local copy only."
        )
    settings = Settings(
        database_url=database_url,
        cookie_secure=False,
        require_verified_email=False,
        default_plan="internal",
        allow_private_targets=True,
        request_timeout_seconds=3.0,
        registrations_per_ip_per_hour=100000,
        scans_per_client_per_hour=100000,
        scans_per_target_per_hour=100000,
    )
    stamp = int(time.time())
    users = []
    with TestClient(create_app(settings, CapturingMailer())) as client:
        for index in range(args.users):
            email = f"lt-{stamp}-{index}@example.com"
            password = secrets.token_urlsafe(18)
            client.cookies.clear()
            client.headers.pop("X-CSRF-Token", None)
            payload = {
                "email": email,
                "password": password,
                "organization_name": f"Load test {index}",
            }
            response = client.post("/api/v1/auth/register", json=payload)
            if response.status_code != 201:
                sys.exit(
                    f"register failed: {response.status_code} {response.text[:200]}"
                )
            client.headers["X-CSRF-Token"] = client.cookies.get("ss_csrf") or ""
            trust_host(client, "127.0.0.1")
            scan = client.post(
                "/api/v1/scans", json={"url": MOCK, "authorization_confirmed": True}
            )
            if scan.status_code != 202:
                sys.exit(f"scan failed to start: {scan.status_code} {scan.text[:200]}")
            scan_id = scan.json()["id"]
            for _ in range(200):
                detail = client.get(f"/api/v1/scans/{scan_id}").json()
                if detail["status"] in ("completed", "failed"):
                    break
                time.sleep(0.05)
            if detail["status"] != "completed":
                sys.exit(f"seed scan did not complete: {detail['status']}")
            users.append({"email": email, "password": password, "scan_id": scan_id})
    Path(args.out).write_text(json.dumps({"users": users}), encoding="utf-8")
    print(f"Created {len(users)} users with one finished scan each -> {args.out}")


if __name__ == "__main__":
    main()
