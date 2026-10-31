"""Load test for App Scanning against a LOCAL copy of the API. Never aim this at the live site.

Measures what the plan allowances depend on (docs/app-scanning-v1-plan-entitlements.md, section 9): how long a
browser upload and a CI submission take by size, what happens when several arrive at once, whether ordinary pages
stay responsive meanwhile, peak memory, and how much database storage one run uses. Results go to
docs/load-test-results.md.

Nothing is sent to OSV.dev: run the server with SECURESCOPE_APP_OSV_ENABLED unset (as in production today).
The extra cost of lookups is measured separately, in-process, against simulated OSV replies (`--osv-bench`).

The server needs App Scanning on, a plan with CI tokens and relaxed rate limits, for example:

    SECURESCOPE_APP_SCANNING_ENABLED=true SECURESCOPE_DEFAULT_PLAN=internal
    SECURESCOPE_APP_SCANS_PER_PROJECT_PER_HOUR=100000 SECURESCOPE_APP_CI_SUBMISSIONS_PER_TOKEN_PER_HOUR=100000
    SECURESCOPE_REGISTRATIONS_PER_IP_PER_HOUR=1000 SECURESCOPE_REQUIRE_VERIFIED_EMAIL=false

    python scripts/loadtest_appscan.py --base http://127.0.0.1:8091 --container lt-api --db-container lt-db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loadtest import check_local

API = "/api/v1"


# --- inputs ------------------------------------------------------------------------------------------------------


def lockfile(packages: int) -> str:
    """A package-lock.json v3 with realistic entries (resolved address and integrity hash, as npm writes them)."""
    entries: dict[str, Any] = {"": {"name": "loadtest", "version": "1.0.0"}}
    for i in range(packages):
        name = f"pkg-{i:05d}"
        entries[f"node_modules/{name}"] = {
            "version": f"{1 + i % 9}.{i % 20}.{i % 7}",
            "resolved": f"https://registry.npmjs.org/{name}/-/{name}-1.0.0.tgz",
            "integrity": "sha512-" + secrets.token_urlsafe(64),
            "license": "MIT",
        }
    return json.dumps(
        {
            "name": "loadtest",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": entries,
        }
    )


def largest_lockfile(limit: int = 2 * 1024 * 1024) -> tuple[int, str]:
    low, high = 1, 20_000
    best = (1, lockfile(1))
    while low <= high:
        mid = (low + high) // 2
        text = lockfile(mid)
        if len(text.encode()) <= limit - 1024:
            best, low = (mid, text), mid + 1
        else:
            high = mid - 1
    return best


def ci_document(project_id: str, findings: int) -> dict[str, Any]:
    items = []
    for i in range(findings):
        if i % 5 == 4:
            items.append(
                {
                    "kind": "secrets",
                    "rule_id": "generic-credential",
                    "severity": "high",
                    "confidence": "medium",
                    "path": f"config/f{i}.yml",
                    "line": i,
                }
            )
        else:
            items.append(
                {
                    "kind": "sast",
                    "rule_id": f"python.lang.security.rule-{i % 40}",
                    "severity": ["low", "medium", "high"][i % 3],
                    "confidence": "medium",
                    "path": f"src/module_{i % 200}/file_{i}.py",
                    "line": 10 + i,
                    "title": f"Rule {i % 40} matched",
                    "message": "Validate this input before it reaches the query.",
                }
            )
    return {
        "schema_version": 1,
        "project_id": project_id,
        "ref": "main@0123456789ab",
        "checks": [
            {
                "kind": "sast",
                "status": "ran",
                "tool": {"name": "semgrep", "version": "1.181.0"},
            },
            {
                "kind": "secrets",
                "status": "ran",
                "tool": {"name": "gitleaks", "version": "8.21.0"},
            },
        ],
        "findings": items,
    }


# --- session ------------------------------------------------------------------------------------------------------


class Session:
    def __init__(self, base: str) -> None:
        self.base = base
        self.client = httpx.Client(base_url=base, timeout=180, headers={"Origin": base})

    def post(self, path: str, **kw: Any) -> httpx.Response:
        headers = {
            "X-CSRF-Token": self.client.cookies.get("ss_csrf") or "",
            **kw.pop("headers", {}),
        }
        return self.client.post(path, headers=headers, **kw)

    def setup(self) -> tuple[str, str]:
        email = f"lt-{secrets.token_hex(4)}@example.com"
        r = self.post(
            f"{API}/auth/register",
            json={"email": email, "password": secrets.token_urlsafe(18)},
        )
        r.raise_for_status()
        project = self.post(
            f"{API}/app/projects", json={"name": f"lt-{secrets.token_hex(3)}"}
        )
        project.raise_for_status()
        token = self.post(f"{API}/api-tokens", json={"name": "lt", "scope": "app"})
        token.raise_for_status()
        return project.json()["id"], token.json()["token"]

    def upload(self, project: str, text: str) -> tuple[float, httpx.Response]:
        body = {
            "project_id": project,
            "kinds": ["dependency"],
            "files": [{"name": "package-lock.json", "content": text}],
        }
        started = time.perf_counter()
        r = self.post(
            f"{API}/app/scans",
            json=body,
            headers={"Idempotency-Key": secrets.token_hex(12)},
        )
        return time.perf_counter() - started, r


def submit(
    base: str, token: str, document: dict[str, Any]
) -> tuple[float, httpx.Response]:
    started = time.perf_counter()
    r = httpx.post(
        f"{base}{API}/app/ci/submissions",
        content=json.dumps(document),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": secrets.token_hex(12),
            "Content-Type": "application/json",
        },
        timeout=180,
    )
    return time.perf_counter() - started, r


# --- measurements -------------------------------------------------------------------------------------------------


class MemoryWatch:
    """Samples the API container's memory with `docker stats` until stopped; keeps the peak."""

    def __init__(self, container: str | None) -> None:
        self.container, self.peak_mb, self._stop = container, 0.0, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while self.container and not self._stop.is_set():
            out = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.MemUsage}}",
                    self.container,
                ],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            value = out.split("/")[0].strip()
            for unit, factor in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1 / 1024)):
                if value.endswith(unit):
                    self.peak_mb = max(
                        self.peak_mb, float(value[: -len(unit)]) * factor
                    )
                    break

    def __enter__(self) -> MemoryWatch:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)


def cpu_seconds(container: str | None) -> float | None:
    """CPU time the API container has used so far (cgroup v2 `usage_usec`). The difference across a request is
    what that request cost, independent of how fast this computer is: divided by 0.1, it is the time the same work
    takes on a host limited to a tenth of a core (Render's free plan)."""
    if not container:
        return None
    out = subprocess.run(
        ["docker", "exec", container, "cat", "/sys/fs/cgroup/cpu.stat"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    usage = next(
        line.split()[1] for line in out.splitlines() if line.startswith("usage_usec")
    )
    return int(usage) / 1_000_000


def cpu_per_call(
    container: str | None, calls: list[Any]
) -> tuple[list[tuple[float, Any]], float | None]:
    """Runs the calls one after another and returns their results and the API's CPU-seconds per call."""
    before = cpu_seconds(container)
    results = [call() for call in calls]
    after = cpu_seconds(container)
    per_call = (
        None
        if before is None or after is None
        else round((after - before) / len(calls), 3)
    )
    return results, per_call


def table_bytes(db_container: str | None) -> dict[str, int] | None:
    if not db_container:
        return None
    sql = (
        "select relname, pg_total_relation_size(c.oid) from pg_class c "
        "where relname in ('app_scans','app_findings') and relkind = 'r'"
    )
    out = subprocess.run(
        [
            "docker",
            "exec",
            db_container,
            "psql",
            "-U",
            "lt",
            "-d",
            "lt",
            "-At",
            "-F",
            "|",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {name: int(size) for name, size in (line.split("|") for line in out.split())}


def summary(times: list[float]) -> str:
    ms = sorted(t * 1000 for t in times)
    p95 = ms[min(len(ms) - 1, round(0.95 * (len(ms) - 1)))]
    return f"p50 {statistics.median(ms):.0f} ms, p95 {p95:.0f} ms, max {ms[-1]:.0f} ms"


async def probe_page(
    base: str, cookies: httpx.Cookies, stop: asyncio.Event
) -> list[float]:
    """Times a signed-in page (who am I) every half second while other work runs."""
    times: list[float] = []
    async with httpx.AsyncClient(base_url=base, cookies=cookies, timeout=60) as client:
        while not stop.is_set():
            started = time.perf_counter()
            await client.get(f"{API}/auth/me")
            times.append(time.perf_counter() - started)
            await asyncio.sleep(0.5)
    return times


async def burst(
    base: str, session: Session, work: list[Any]
) -> tuple[list[tuple[float, int]], list[float]]:
    stop = asyncio.Event()
    probe = asyncio.create_task(probe_page(base, session.client.cookies, stop))
    results = await asyncio.gather(*(asyncio.to_thread(w) for w in work))
    stop.set()
    return [(t, r.status_code) for t, r in results], await probe


def osv_bench(packages: int, advisories_every: int) -> dict[str, float]:
    """CPU cost of the OSV source and the result mapping, against simulated OSV replies (no network)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app.appscan.manifests import parse_manifest
    from app.appscan.pipeline import run_dependency_scan
    from app.services.osv import OsvSource

    record = {
        "id": "GHSA-0000-0000-0000",
        "summary": "Simulated advisory",
        "aliases": ["CVE-2026-0000"],
        "database_specific": {"severity": "HIGH"},
        "affected": [],
        "references": [{"url": "https://github.com/advisories/GHSA-0000-0000-0000"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/querybatch":
            queries = json.loads(request.content)["queries"]
            results = [
                {"vulns": [{"id": "GHSA-0000-0000-0000", "modified": "x"}]}
                if i % advisories_every == 0
                else {}
                for i, _ in enumerate(queries)
            ]
            return httpx.Response(200, json={"results": results})
        return httpx.Response(200, json=record)

    text = lockfile(packages) if packages else largest_lockfile()[1]
    parsed = [parse_manifest("package-lock.json", text.encode())]
    source = OsvSource(transport=httpx.MockTransport(handler), budget_seconds=600)
    started_cpu, started = time.process_time(), time.perf_counter()
    outcome = run_dependency_scan("bench", parsed, source, budget_seconds=600)
    return {
        "packages": len(parsed[0].packages),
        "findings": len(outcome.findings),
        "cpu_s_one_core": round(time.process_time() - started_cpu, 3),
        "wall_s": round(time.perf_counter() - started, 3),
    }


# --- main ---------------------------------------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:8091")
    parser.add_argument("--container", help="API container name, for peak memory")
    parser.add_argument(
        "--db-container",
        help="PostgreSQL container name (user and database 'lt'), for storage",
    )
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--osv-bench",
        action="store_true",
        help="only run the in-process OSV cost measurement",
    )
    args = parser.parse_args()

    if args.osv_bench:
        for packages, every in (
            (1000, 20),
            (5000, 20),
            (0, 20),
        ):  # 0: the largest file under 2 MB
            print(json.dumps(osv_bench(packages, every)))
        return

    check_local(args.base)
    report: dict[str, Any] = {}
    session = Session(args.base)
    project, token = session.setup()
    session.client.get(f"{API}/app/overview").raise_for_status()

    with MemoryWatch(args.container) as memory:
        largest, largest_text = largest_lockfile()
        sizes = [
            (10, lockfile(10)),
            (1000, lockfile(1000)),
            (5000, lockfile(5000)),
            (largest, largest_text),
        ]
        uploads = []
        for packages, text in sizes:
            done, cpu = cpu_per_call(
                args.container,
                [
                    lambda text=text: session.upload(project, text)
                    for _ in range(args.repeat)
                ],
            )
            times = [t for t, _ in done]
            results = {
                f"{r.status_code} {r.json().get('result', r.json().get('detail'))}"
                for _, r in done
            }
            uploads.append(
                {
                    "packages": packages,
                    "kb": len(text.encode()) // 1024,
                    "time": summary(times),
                    "cpu_s_per_run": cpu,
                    "results": sorted(results),
                }
            )
            print("upload", uploads[-1], flush=True)
        report["uploads"] = uploads

        submissions = []
        for findings in (0, 25, 500, 5000):
            document = ci_document(project, findings)
            done, cpu = cpu_per_call(
                args.container,
                [
                    lambda document=document: submit(args.base, token, document)
                    for _ in range(args.repeat)
                ],
            )
            times = [t for t, _ in done]
            results = {
                f"{r.status_code} {r.json().get('result', r.json().get('detail'))}"
                for _, r in done
            }
            submissions.append(
                {
                    "findings": findings,
                    "kb": len(json.dumps(document)) // 1024,
                    "time": summary(times),
                    "cpu_s_per_run": cpu,
                    "results": sorted(results),
                }
            )
            print("submission", submissions[-1], flush=True)
        report["submissions"] = submissions

        upload_text = lockfile(1000)
        work = [lambda: session.upload(project, upload_text) for _ in range(5)]
        done, page = asyncio.run(burst(args.base, session, work))
        report["burst_uploads"] = {
            "count": 5,
            "time": summary([t for t, _ in done]),
            "statuses": sorted({s for _, s in done}),
            "signed_in_page_meanwhile": summary(page),
        }
        print("burst uploads", report["burst_uploads"], flush=True)

        document = ci_document(project, 500)
        work = [lambda: submit(args.base, token, document) for _ in range(5)]
        done, page = asyncio.run(burst(args.base, session, work))
        report["burst_submissions"] = {
            "count": 5,
            "time": summary([t for t, _ in done]),
            "statuses": sorted({s for _, s in done}),
            "signed_in_page_meanwhile": summary(page),
        }
        print("burst submissions", report["burst_submissions"], flush=True)

        before = table_bytes(args.db_container)
        typical = ci_document(project, 25)
        for _ in range(50):
            submit(args.base, token, typical)
        after = table_bytes(args.db_container)
        if before and after:
            grown = sum(after.values()) - sum(before.values())
            report["storage"] = {
                "runs": 50,
                "findings_each": 25,
                "bytes_per_run": grown // 50,
                "tables": after,
            }
            print("storage", report["storage"], flush=True)
    report["peak_memory_mb"] = round(memory.peak_mb, 1)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
