"""Load tests for a LOCAL copy of the SecureScope API. Never aim this at the live site.

It measures how many requests per second the API answers, how long they take, what it does when it is
overloaded, and whether the abuse limits hold. It refuses any address that is not this computer, unless the
environment variable LOADTEST_ALLOW_REMOTE is set to "yes-this-server-is-mine" (do not use that on the live
service: a free host would be throttled or suspended, and other people's visitors would feel it).

Set-up (see docs/load-test-results.md for the full steps):

    python scripts/loadtest_mock.py &                       # a tiny site to scan
    python scripts/loadtest_seed.py --users 20 --out /tmp/lt-users.json
    python scripts/loadtest.py --scenario capacity --users-file /tmp/lt-users.json --pid <server pid>

Scenarios: capacity, signin-blocking and heavy (need relaxed limits); abuse (needs the real limits).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import statistics
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
ALLOW_REMOTE = "yes-this-server-is-mine"


def check_local(base: str) -> None:
    host = urlsplit(base).hostname or ""
    if (
        host not in LOCAL_HOSTS
        and os.environ.get("LOADTEST_ALLOW_REMOTE") != ALLOW_REMOTE
    ):
        sys.exit(
            f"Refusing to load-test {host!r}: only this computer is allowed (see the file header)."
        )


def rss_mb(pid: int | None) -> float | None:
    if pid is None:
        return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


class Result:
    def __init__(self, name: str, concurrency: int) -> None:
        self.name = name
        self.concurrency = concurrency
        self.latencies: list[float] = []
        self.statuses: Counter[str] = Counter()
        self.seconds = 0.0

    def add(self, status: int | str, seconds: float) -> None:
        self.statuses[str(status)] += 1
        self.latencies.append(seconds * 1000)

    def row(self) -> dict[str, object]:
        total = len(self.latencies)
        server_errors = sum(
            n
            for s, n in self.statuses.items()
            if s.startswith("5") or s in ("error", "timeout")
        )
        return {
            "name": self.name,
            "concurrency": self.concurrency,
            "requests": total,
            "per_second": round(total / self.seconds, 1) if self.seconds else 0,
            "p50_ms": round(statistics.median(self.latencies), 1) if total else 0,
            "p95_ms": round(percentile(self.latencies, 95), 1),
            "p99_ms": round(percentile(self.latencies, 99), 1),
            "max_ms": round(max(self.latencies), 1) if total else 0,
            "statuses": dict(sorted(self.statuses.items())),
            "server_errors": server_errors,
        }


async def timed(result: Result, call: Callable[[], Awaitable[httpx.Response]]) -> None:
    started = time.perf_counter()
    try:
        response = await call()
        result.add(response.status_code, time.perf_counter() - started)
    except httpx.TimeoutException:
        result.add("timeout", time.perf_counter() - started)
    except httpx.HTTPError:
        result.add("error", time.perf_counter() - started)


async def run_level(
    name: str,
    concurrency: int,
    seconds: float,
    clients: list[httpx.AsyncClient],
    action: Callable[[httpx.AsyncClient, int], Awaitable[httpx.Response]],
) -> Result:
    result = Result(name, concurrency)
    stop = time.perf_counter() + seconds

    async def worker(index: int) -> None:
        client = clients[index % len(clients)]
        counter = 0
        while time.perf_counter() < stop:
            counter += 1
            await timed(result, lambda n=counter: action(client, n))

    started = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(concurrency)))
    result.seconds = time.perf_counter() - started
    return result


def make_client(base: str, timeout: float = 30.0) -> httpx.AsyncClient:
    limits = httpx.Limits(max_connections=400, max_keepalive_connections=400)
    return httpx.AsyncClient(base_url=base, timeout=timeout, limits=limits)


async def sign_in(base: str, user: dict[str, str]) -> httpx.AsyncClient:
    client = make_client(base)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    if response.status_code != 200:
        sys.exit(
            f"sign-in failed for a seeded user: {response.status_code} (are the limits relaxed?)"
        )
    client.headers["X-CSRF-Token"] = client.cookies.get("ss_csrf") or ""
    return client


def print_table(results: list[Result]) -> None:
    print(
        "| Test | Users | Requests | Per second | p50 ms | p95 ms | p99 ms | Max ms | Statuses |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        row = r.row()
        statuses = ", ".join(f"{k}:{v}" for k, v in row["statuses"].items())  # type: ignore[attr-defined]
        print(
            f"| {row['name']} | {row['concurrency']} | {row['requests']} | {row['per_second']} | {row['p50_ms']} "
            f"| {row['p95_ms']} | {row['p99_ms']} | {row['max_ms']} | {statuses} |"
        )


async def health_after(base: str, label: str) -> bool:
    async with make_client(base, timeout=10) as client:
        try:
            ready = (await client.get("/api/v1/ready")).status_code == 200
        except httpx.HTTPError:
            ready = False
    print(f"- {label}: ready check {'OK' if ready else 'FAILED'}")
    return ready


async def capacity(
    base: str, users: list[dict[str, str]], seconds: float, pid: int | None
) -> list[Result]:
    results: list[Result] = []
    print(f"Server memory before: {rss_mb(pid)} MB")
    async with make_client(base) as anon:
        for level in (1, 10, 50, 100, 200):
            results.append(
                await run_level(
                    "health",
                    level,
                    seconds,
                    [anon],
                    lambda c, n: c.get("/api/v1/health"),
                )
            )
    clients = [await sign_in(base, u) for u in users]
    reads = ["/api/v1/auth/me", "/api/v1/overview", "/api/v1/scans", "/api/v1/targets"]
    for level in (1, 10, 50, 100):
        results.append(
            await run_level(
                "signed-in reads",
                level,
                seconds,
                clients,
                lambda c, n: c.get(reads[n % len(reads)]),
            )
        )
    for client in clients:
        await client.aclose()
    for level in (1, 4, 16):
        pool = [make_client(base) for _ in range(level)]
        creds = [users[i % len(users)] for i in range(level)]

        async def login(
            c: httpx.AsyncClient,
            n: int,
            creds: list[dict[str, str]] = creds,
            pool: list[httpx.AsyncClient] = pool,
        ) -> httpx.Response:
            user = creds[pool.index(c)]
            return await c.post(
                "/api/v1/auth/login",
                json={"email": user["email"], "password": user["password"]},
            )

        results.append(
            await run_level("sign-in (password check)", level, seconds, pool, login)
        )
        for c in pool:
            await c.aclose()
    print(f"Server memory after: {rss_mb(pid)} MB")
    return results


async def signins_vs_everyone_else(
    base: str, users: list[dict[str, str]], seconds: float
) -> list[Result]:
    """Do password checks make the rest of the site wait? Sign in 8 at a time while one visitor loads a page."""
    pool = [make_client(base) for _ in range(8)]
    probe = Result("page load while 8 people sign in", 1)
    logins = Result("(the 8 sign-ins)", 8)
    stop = time.perf_counter() + seconds

    async def signer(index: int) -> None:
        user = users[index % len(users)]
        while time.perf_counter() < stop:
            await timed(
                logins,
                lambda: pool[index].post(
                    "/api/v1/auth/login",
                    json={"email": user["email"], "password": user["password"]},
                ),
            )

    async def visitor() -> None:
        async with make_client(base) as client:
            while time.perf_counter() < stop:
                await timed(probe, lambda: client.get("/api/v1/health"))
                await asyncio.sleep(0.05)

    started = time.perf_counter()
    await asyncio.gather(visitor(), *(signer(i) for i in range(8)))
    probe.seconds = logins.seconds = time.perf_counter() - started
    for client in pool:
        await client.aclose()
    return [probe, logins]


async def heavy(
    base: str, users: list[dict[str, str]], pid: int | None
) -> list[Result]:
    """Scans and PDF reports: slow, limited jobs. Each simulated person asks once."""
    results: list[Result] = []
    clients = [await sign_in(base, u) for u in users]

    async def first_pdf(c: httpx.AsyncClient, user: dict[str, str]) -> httpx.Response:
        return await c.get(f"/api/v1/scans/{user['scan_id']}/report/pdf")

    for level in (1, 4):
        result = Result("PDF report, first build", level)
        group = list(zip(clients, users, strict=True))[:level]
        started = time.perf_counter()
        await asyncio.gather(
            *(timed(result, lambda c=c, u=u: first_pdf(c, u)) for c, u in group)
        )  # type: ignore[misc]
        result.seconds = time.perf_counter() - started
        results.append(result)
        users, clients = (
            users[level:],
            clients[level:],
        )  # a report is built once; use fresh people next time
    for level in (1, 5, 15):
        result = Result("start a scan and wait for it", level)
        group = clients[:level]

        async def one_scan(c: httpx.AsyncClient) -> httpx.Response:
            created = await c.post(
                "/api/v1/scans",
                json={
                    "url": "http://127.0.0.1:8765/plain",
                    "authorization_confirmed": True,
                },
            )
            if created.status_code != 202:
                return created
            scan_id = created.json()["id"]
            for _ in range(600):
                detail = await c.get(f"/api/v1/scans/{scan_id}")
                if detail.json().get("status") in ("completed", "failed"):
                    return detail
                await asyncio.sleep(0.2)
            raise httpx.ReadTimeout("scan did not finish")

        started = time.perf_counter()
        await asyncio.gather(*(timed(result, lambda c=c: one_scan(c)) for c in group))  # type: ignore[misc]
        result.seconds = time.perf_counter() - started
        results.append(result)
    for client in clients:
        await client.aclose()
    print(f"Server memory after heavy jobs: {rss_mb(pid)} MB")
    return results


async def abuse(
    base: str, users: list[dict[str, str]], pid: int | None
) -> list[Result]:
    """With the real limits on: wrong passwords, mass sign-ups and scan floods must be stopped, never crash."""
    results: list[Result] = []
    async with make_client(base) as client:
        wrong = Result("wrong password, one account", 1)
        started = time.perf_counter()
        for _ in range(40):
            await timed(
                wrong,
                lambda: client.post(
                    "/api/v1/auth/login",
                    json={
                        "email": users[0]["email"],
                        "password": secrets.token_urlsafe(12),
                    },
                ),
            )
        wrong.seconds = time.perf_counter() - started
        results.append(wrong)
        await health_after(base, "after wrong-password flood")

        mass = Result("many sign-ups from one address", 1)
        started = time.perf_counter()
        for i in range(30):
            body = {
                "email": f"abuse-{int(time.time())}-{i}@example.com",
                "password": secrets.token_urlsafe(16),
            }
            await timed(
                mass, lambda body=body: client.post("/api/v1/auth/register", json=body)
            )  # type: ignore[misc]
        mass.seconds = time.perf_counter() - started
        results.append(mass)
        await health_after(base, "after sign-up flood")

        # Hammering one URL from many connections at once: the server must keep answering.
        burst = await run_level(
            "500 connections at once, unauthenticated",
            500,
            5,
            [client],
            lambda c, n: c.get("/api/v1/auth/me"),
        )
        results.append(burst)
        await health_after(base, "after 500 simultaneous connections")
    scanner = await sign_in(base, users[1])
    flood = Result("scan flood, one account", 1)
    started = time.perf_counter()
    for _ in range(15):
        await timed(
            flood,
            lambda: scanner.post(
                "/api/v1/scans",
                json={
                    "url": "http://127.0.0.1:8765/plain",
                    "authorization_confirmed": True,
                },
            ),
        )
    flood.seconds = time.perf_counter() - started
    results.append(flood)
    await scanner.aclose()
    await health_after(base, "after scan flood")
    print(f"Server memory after abuse: {rss_mb(pid)} MB")
    return results


async def main_async(args: argparse.Namespace) -> None:
    users = json.loads(Path(args.users_file).read_text(encoding="utf-8"))["users"]
    if not await health_after(args.base, "before"):
        sys.exit("The server is not answering.")
    if args.scenario == "capacity":
        results = await capacity(args.base, users, args.seconds, args.pid)
    elif args.scenario == "signin-blocking":
        results = await signins_vs_everyone_else(args.base, users, args.seconds)
    elif args.scenario == "heavy":
        results = await heavy(args.base, users, args.pid)
    else:
        results = await abuse(args.base, users, args.pid)
    print()
    print_table(results)
    await health_after(args.base, "after everything")
    if args.json:
        Path(args.json).write_text(
            json.dumps([r.row() for r in results], indent=2), encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--scenario",
        choices=["capacity", "signin-blocking", "heavy", "abuse"],
        required=True,
    )
    parser.add_argument("--users-file", required=True)
    parser.add_argument(
        "--seconds", type=float, default=6.0, help="how long each load level runs"
    )
    parser.add_argument(
        "--pid", type=int, default=None, help="server process id, to report its memory"
    )
    parser.add_argument(
        "--json", default=None, help="also write the numbers to this file"
    )
    args = parser.parse_args()
    check_local(args.base)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
