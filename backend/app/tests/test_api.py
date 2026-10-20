from __future__ import annotations

import time

from fastapi.testclient import TestClient


def start_scan(client: TestClient, url: str, confirmed: bool = True):  # type: ignore[no-untyped-def]
    return client.post("/api/v1/scans", json={"url": url, "authorization_confirmed": confirmed})


def wait_for(client: TestClient, scan_id: str, timeout: float = 15.0) -> dict:  # type: ignore[type-arg]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/scans/{scan_id}").json()
        if data["status"] in ("completed", "failed"):
            return data  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")


def test_health(strict_client: TestClient) -> None:
    body = strict_client.get("/api/v1/health").json()
    assert body == {"status": "ok", "version": "0.7.0"}


def test_security_headers_on_api_responses(strict_client: TestClient) -> None:
    response = strict_client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_cors_only_allows_configured_origins(strict_client: TestClient) -> None:
    ok = strict_client.get("/api/v1/health", headers={"Origin": "http://localhost:8080"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8080"
    bad = strict_client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_authorization_must_be_confirmed(strict_client: TestClient) -> None:
    response = start_scan(strict_client, "https://example.com/", confirmed=False)
    assert response.status_code == 400
    assert "authorization" in response.json()["detail"].lower()
    assert strict_client.get("/api/v1/scans").json()["total"] == 0  # nothing was stored


def test_missing_fields_are_validation_errors(strict_client: TestClient) -> None:
    assert strict_client.post("/api/v1/scans", json={}).status_code == 422
    assert strict_client.post("/api/v1/scans", json={"url": "https://example.com"}).status_code == 422


def test_server_side_rejection_of_internal_targets(strict_client: TestClient) -> None:
    for url in [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://user:pw@example.com/",
        "file:///etc/passwd",
        "http://example.com:22/",
    ]:
        response = start_scan(strict_client, url)
        assert response.status_code == 400, url
        assert response.json()["detail"]
    assert strict_client.get("/api/v1/scans").json()["total"] == 0


def test_end_to_end_scan_with_findings_and_exports(local_client: TestClient, mock_server: str) -> None:
    created = start_scan(local_client, f"{mock_server}/plain")
    assert created.status_code == 202
    scan_id = created.json()["id"]
    detail = wait_for(local_client, scan_id)
    assert detail["status"] == "completed"
    assert detail["metadata"]["status_code"] == 200
    assert detail["metadata"]["resolved_addresses"] == ["127.0.0.1"]
    found = {f["id"] for f in detail["findings"]}
    assert {
        "SS-TLS-001",
        "SS-HDR-CSP-001",
        "SS-HDR-XCTO-001",
        "SS-HDR-REF-001",
        "SS-HDR-PERM-001",
        "SS-DISC-SRV-001",
        "SS-DISC-XPB-001",
        "SS-COOKIE-HTTPONLY-001",
        "SS-COOKIE-SAMESITE-001",
    } <= found
    assert "SS-HDR-HSTS-001" not in found  # not meaningful over plain HTTP
    assert 0 <= detail["score"] < 100 and detail["grade"] in "ABCDF"
    assert "not proof" in detail["score_note"]
    assert "SECRETVALUE" not in str(detail)  # cookie values are never stored
    for finding in detail["findings"]:
        assert finding["title"] and finding["description"] and finding["remediation"]

    listing = local_client.get("/api/v1/scans").json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == scan_id
    assert listing["items"][0]["counts"]["high"] >= 1

    report_json = local_client.get(f"/api/v1/scans/{scan_id}/report?format=json")
    assert report_json.status_code == 200 and report_json.json()["id"] == scan_id
    assert "attachment" in report_json.headers["content-disposition"]
    report_md = local_client.get(f"/api/v1/scans/{scan_id}/report?format=md")
    assert report_md.text.startswith("# SecureScope report")
    report_html = local_client.get(f"/api/v1/scans/{scan_id}/report?format=html")
    assert report_html.headers["content-type"].startswith("text/html")
    assert "style-src 'unsafe-inline'" in report_html.headers["content-security-policy"]
    assert local_client.get(f"/api/v1/scans/{scan_id}/report?format=docx").status_code == 422


def test_hardened_target_has_only_the_expected_findings(local_client: TestClient, mock_server: str) -> None:
    detail = wait_for(local_client, start_scan(local_client, f"{mock_server}/hardened").json()["id"])
    # Only: served over plain http, the server announces its name (no version), and no security.txt.
    ids = {f["id"] for f in detail["findings"]}
    assert ids == {"SS-TLS-001", "SS-DISC-SRV-002", "SS-DISC-SEC-001"}


def test_directory_listing_detected(local_client: TestClient, mock_server: str) -> None:
    detail = wait_for(local_client, start_scan(local_client, f"{mock_server}/listing").json()["id"])
    assert "SS-DIR-001" in {f["id"] for f in detail["findings"]}


def test_redirects(local_client: TestClient, mock_server: str) -> None:
    same = wait_for(local_client, start_scan(local_client, f"{mock_server}/redirect-same").json()["id"])
    assert same["status"] == "completed" and len(same["metadata"]["redirect_chain"]) == 2
    off = wait_for(local_client, start_scan(local_client, f"{mock_server}/redirect-off").json()["id"])
    assert off["status"] == "completed"
    assert off["metadata"]["off_origin_redirect"] == "http://other.example.org"
    assert "SS-SCOPE-001" in {f["id"] for f in off["findings"]}


def test_redirect_loop_fails_cleanly(local_client: TestClient, mock_server: str) -> None:
    detail = wait_for(local_client, start_scan(local_client, f"{mock_server}/redirect-loop").json()["id"])
    assert detail["status"] == "failed" and "redirect" in detail["error"].lower()
    assert local_client.get(f"/api/v1/scans/{detail['id']}/report?format=json").status_code == 200


def test_slow_target_times_out(local_client: TestClient, mock_server: str) -> None:
    detail = wait_for(local_client, start_scan(local_client, f"{mock_server}/slow").json()["id"])
    assert detail["status"] == "failed" and "in time" in detail["error"]


def test_large_response_is_handled(local_client: TestClient, mock_server: str) -> None:
    detail = wait_for(local_client, start_scan(local_client, f"{mock_server}/big").json()["id"])
    assert detail["status"] == "completed"


def test_unknown_and_malformed_ids_return_404(strict_client: TestClient) -> None:
    assert strict_client.get("/api/v1/scans/doesnotexist").status_code == 404
    assert strict_client.get("/api/v1/scans/..%2F..%2Fetc").status_code == 404
    assert strict_client.get("/api/v1/scans/abc/report").status_code == 404


def test_per_target_rate_limit(local_client: TestClient, mock_server: str) -> None:
    for _ in range(3):
        assert start_scan(local_client, f"{mock_server}/hardened").status_code == 202
    blocked = start_scan(local_client, f"{mock_server}/hardened")
    assert blocked.status_code == 429


def test_pagination_bounds(strict_client: TestClient) -> None:
    assert strict_client.get("/api/v1/scans?limit=0").status_code == 422
    assert strict_client.get("/api/v1/scans?limit=101").status_code == 422
    assert strict_client.get("/api/v1/scans?offset=-1").status_code == 422


def test_ready_reports_database_state(strict_client: TestClient) -> None:
    ok = strict_client.get("/api/v1/ready")
    assert ok.status_code == 200 and ok.json() == {"status": "ready"}


def test_ready_returns_503_without_leaking_details(strict_client: TestClient) -> None:
    strict_client.app.state.s.repo.ping = lambda: (_ for _ in ()).throw(RuntimeError("password=secret"))  # type: ignore[attr-defined]
    response = strict_client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "secret" not in response.text
